"""Exercise actual sensor methods without installing the HA runtime."""
import ast
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo
import unittest

PATH = Path(__file__).resolve().parents[1] / 'custom_components/waste_management/sensor.py'

class Base:
    async def async_added_to_hass(self): pass
    async def async_will_remove_from_hass(self): pass
    async def async_get_last_state(self): return self.previous

class SensorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 3, 13, tzinfo=timezone.utc)
        self.zone = ZoneInfo('America/New_York')
        self.dt = SimpleNamespace(utcnow=lambda: self.now, now=lambda: self.now.astimezone(self.zone),
            as_local=lambda v:v.astimezone(self.zone), parse_datetime=lambda v:self.parse(v))
        self.client = SimpleNamespace(async_authenticate=AsyncMock(), async_okta_authorize=AsyncMock(),
            async_get_service_pickup=AsyncMock(return_value=[datetime(2026,11,4,5,tzinfo=timezone.utc)]))
        self.cancel=Mock()
        self.ns = dict(asyncio=asyncio, datetime=datetime,time=__import__('datetime').time,timedelta=timedelta,
            dt_util=self.dt, _LOGGER=Mock(), RETRY_SECONDS=3600, REQUEST_TIMEOUT=90,
            WMClient=Mock(return_value=self.client),get_async_client=Mock(return_value='shared'),
            async_call_later=Mock(return_value=self.cancel),SensorEntity=Base,RestoreEntity=object,
            CONF_ACCOUNT='account',CONF_SERVICES='services',CONF_OFFSET_DAYS='offset_days',
            CONF_USERNAME='username',CONF_PASSWORD='password',DOMAIN='waste_management')
        tree=ast.parse(PATH.read_text(encoding='utf-8-sig'))
        tree.body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))]
        exec(compile(tree,str(PATH),'exec'),self.ns)
        self.entity=self.ns['WasteManagementSensorEntity'](SimpleNamespace(config=SimpleNamespace(components=set())),
            'Trash','test','test','account','trash',None)
        self.entity.previous=None
        self.entity.entity_id='sensor.trash'
    def parse(self,v):
        try:return datetime.fromisoformat(v)
        except (ValueError,TypeError):return None
    async def test_success_schedules_next_local_day(self):
        await self.entity.async_update()
        self.assertEqual(self.entity._next_refresh.astimezone(self.zone).isoformat(),'2026-11-04T00:05:00-05:00')
        self.assertFalse(self.entity._stale)
        self.ns['WMClient'].assert_called_once_with('test','test','shared')
    async def test_outage_retains_date_and_retries_hourly_then_recovers(self):
        await self.entity.async_update()
        value=self.entity._attr_native_value
        self.client.async_get_service_pickup.side_effect=TimeoutError()
        await self.entity.async_update()
        self.assertEqual(self.entity._attr_native_value,value)
        self.assertTrue(self.entity._attr_available)
        self.assertTrue(self.entity._stale)
        self.assertEqual(self.entity._next_refresh,self.now+timedelta(hours=1))
        self.client.async_get_service_pickup.side_effect=None
        await self.entity.async_update()
        self.assertFalse(self.entity._stale)
        self.assertIsNone(self.entity._last_error)
    async def test_no_cache_does_not_make_up_schedule(self):
        self.client.async_authenticate.side_effect=TimeoutError()
        await self.entity.async_update()
        self.assertFalse(self.entity._attr_available)
        self.assertIsNone(self.entity._attr_native_value)
    async def test_malformed_or_empty_response_keeps_cache(self):
        await self.entity.async_update()
        value=self.entity._attr_native_value
        for result in ([],None,['invalid']):
            self.client.async_get_service_pickup.return_value=result
            await self.entity.async_update()
            self.assertTrue(self.entity._stale)
            self.assertEqual(self.entity._attr_native_value,value)
    async def test_restore_after_failure_and_restart(self):
        self.entity.previous=SimpleNamespace(state='2026-11-04T05:00:00+00:00',attributes={
            'last_successful_refresh':'2026-11-02T05:05:00+00:00','data_stale':True,
            'next_refresh':(self.now+timedelta(minutes=25)).isoformat()})
        await self.entity.async_added_to_hass()
        self.assertTrue(self.entity._attr_available)
        self.assertTrue(self.entity._stale)
        self.assertEqual(self.entity._next_refresh,self.now+timedelta(minutes=25))
    async def test_same_day_success_does_not_fetch_on_restart(self):
        self.entity.previous=SimpleNamespace(state='2026-11-04T05:00:00+00:00',attributes={
            'last_successful_refresh':self.now.isoformat(),'data_stale':False})
        await self.entity.async_added_to_hass()
        self.client.async_authenticate.assert_not_awaited()
        self.assertEqual(self.entity._next_refresh.day,4)
    async def test_past_date_is_never_advanced(self):
        self.client.async_get_service_pickup.return_value=[self.now-timedelta(days=2)]
        await self.entity.async_update()
        self.assertTrue(self.entity.extra_state_attributes['pickup_date_passed'])
        self.assertEqual(self.entity._attr_native_value,self.now-timedelta(days=2))
    async def test_offsets_and_unique_id_preserved(self):
        for offset in (None,0,-2,3):
            e=self.ns['WasteManagementSensorEntity'](self.entity.hass,'Trash','t','t','account','trash',offset)
            await e.async_update()
            self.assertEqual(e._attr_unique_id,'account_trash')
            self.assertEqual(e._attr_native_value,self.client.async_get_service_pickup.return_value[0]+timedelta(days=offset or 0))
    async def test_shutdown_cancels_timer(self):
        await self.entity.async_update()
        await self.entity.async_will_remove_from_hass()
        self.cancel.assert_called()
        self.assertIsNone(self.entity._cancel_refresh)
    async def test_setup_existing_entity_without_network(self):
        registry=SimpleNamespace(async_get_entity_id=Mock(return_value='sensor.trash'),
            async_get=Mock(return_value=SimpleNamespace(original_name='96 Gallon Toter',name=None)))
        self.ns['er']=SimpleNamespace(async_get=Mock(return_value=registry))
        added=Mock()
        await self.ns['async_setup_entry'](self.entity.hass,SimpleNamespace(data=dict(
            username='u',password='p',account='account',services=['trash'])),added)
        self.client.async_authenticate.assert_not_awaited()
        self.assertEqual(added.call_args.args[0][0]._attr_name,'96 Gallon Toter')
        self.assertFalse(added.call_args.args[1])
    def test_dst_daily_schedule(self):
        now=datetime(2026,11,1,4,30,tzinfo=timezone.utc)
        self.assertEqual(self.ns['next_daily_refresh'](now).isoformat(),'2026-11-02T00:05:00-05:00')

if __name__=='__main__':unittest.main()

