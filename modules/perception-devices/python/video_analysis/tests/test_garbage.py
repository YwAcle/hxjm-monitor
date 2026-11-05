import os
import unittest
from unittest.mock import patch
import numpy as np
from video_analysis.algorithms import algorithm_spec
from video_analysis.garbage_adapter import garbage_results
from video_analysis.result_publisher import ResultPublisher
from video_analysis.tests.test_persistence import capture


class GarbageTests(unittest.TestCase):
    def test_reuses_detector_and_converts_pixels_without_navigation(self):
        with patch.dict(os.environ, {'GARBAGE_MODEL_PATH':'/local/model'}), patch('garbage_detection.detector.Detector') as model:
            model.return_value.infer.return_value={'targets':[{'label':'瓶罐类','bbox':[100,200,300,400],'confidence':.8}], 'inference_seconds':2}
            adapter=algorithm_spec('garbage').create()
            detections, ms=adapter.infer(np.zeros((10,10,3),dtype=np.uint8),{})
            self.assertEqual(detections[0]['bbox'],[.1,.2,.3,.4])
            self.assertEqual(ms,2000)
            model.assert_called_once_with('/local/model','cpu')
            self.assertFalse(algorithm_spec('garbage').tracking)

    def test_request_reuses_spool_id_time_and_standard_garbage_schema(self):
        from video_analysis.tracking_state import frame_fact, instant
        fact=frame_fact(capture(),[dict(label='瓶罐类',bbox=[.1,.2,.3,.4],confidence=.8,track_id=0,is_prediction=False)], {'瓶罐类':'garbage'})
        publisher=object.__new__(ResultPublisher)
        context=dict(id='ctx',result_set_id='set',context_key='key',started_at=fact['occurred_at'],capability_code='garbage.detection',result_type='garbage.detection',started={'task_id':'task','run_id':'run'})
        job={'payload':{'frame':fact,'processed_at':fact['occurred_at']}}
        request=publisher._frame_request(context,{'source':'src','id':'session'},[(None,job)])
        self.assertEqual(request['result_type'],'garbage.detection')
        result=request['results'][0]
        self.assertEqual(result['result_id'],fact['result_id'])
        self.assertEqual(result['start_at'],fact['occurred_at'])
        self.assertEqual(result['payload']['targets'][0]['category'],'瓶罐类')
        self.assertNotIn('tracklet_id',result)
        self.assertEqual(request['analysis_coverage']['result_ids'],[fact['result_id']])
        self.assertEqual(request['analysis_coverage']['analyzed_frame_count'],0)
        self.assertFalse(garbage_results([dict(fact,targets=[])])[0]['payload']['has_target'])

    def test_spool_delivery_and_close_do_not_create_person_tracks(self):
        from video_analysis.tests.test_persistence import PersistenceTests
        fixture=PersistenceTests()
        fixture.setUp()
        try:
            fixture.config.implementation_code='garbage'
            fixture.config.capability_code='garbage.detection'
            original=fixture.api.call
            fixture.api.call=lambda path,body=None: dict(items=[dict(implementation_code='garbage',implementation_version='test-v1')]) if path.startswith('/instances?') else original(path,body)
            frame=capture()
            context=fixture.publisher._begin_frame('camera_1',frame,'service','component')
            fixture.publisher._record(context,frame,[dict(label='瓶罐类',bbox=[.1,.2,.3,.4],confidence=.8,track_id=0,is_prediction=False)],frame.frame_ts_ms+10,[])
            fixture.publisher._interrupt('camera_1','manual-stop',True)
            fixture.drain()
            requests=[b for p,b in fixture.api.calls if p=='/results/register']
            self.assertEqual(requests[0]['result_type'],'garbage.detection')
            self.assertEqual(requests[0]['results'][0]['payload']['targets'][0]['category'],'瓶罐类')
            closes=[b for p,b in fixture.api.calls if p=='/tracking/close']
            self.assertTrue(closes[0]['close_context'])
            self.assertEqual(fixture.publisher.spool.all_states(),[])
        finally:
            fixture.doCleanups()
