import json
import zstandard as zstd
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from soroscan.ingest.models import TrackedContract, ContractEvent

class CompressedJSONFieldTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="compress_test_user")
        self.contract = TrackedContract.objects.create(
            contract_id="C" + "A" * 55,
            name="Test Contract",
            owner=self.user,
        )

    def test_save_and_retrieve_compressed_payload(self):
        payload_data = {"key": "value", "large": "x" * 5000}
        
        event = ContractEvent.objects.create(
            contract=self.contract,
            event_type="test",
            payload=payload_data,
            payload_hash="testhash",
            ledger=100,
            timestamp="2023-01-01T00:00:00Z",
            tx_hash="txhash"
        )
        
        # Retrieve fresh from DB
        event.refresh_from_db()
        self.assertEqual(event.payload, payload_data)
        
    def test_backward_compatibility_uncompressed_data(self):
        # Insert uncompressed data directly into DB
        payload_data = {"old": "data"}
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ingest_contractevent 
                (contract_id, event_type, payload, payload_hash, ledger, event_index, timestamp, tx_hash, validation_status, raw_xdr, status, decoding_status, signature_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [self.contract.id, 'old_test', json.dumps(payload_data).encode('utf-8'), 'hash', 101, 0, '2023-01-01 00:00:00+00', 'tx', 'passed', '', 'CONFIRMED', 'no_abi', 'missing']
            )
            
        event = ContractEvent.objects.get(event_type='old_test')
        print(f"DEBUG_PAYLOAD: type={type(event.payload)}, val={event.payload!r}")
        self.assertEqual(event.payload, payload_data)


class ZstdMiddlewareTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_zstd_middleware_compresses(self):
        from django.http import HttpResponse
        from soroscan.middleware_zstd import ZstdMiddleware

        content = b"x" * 2048
        def get_response(request):
            return HttpResponse(content, content_type="application/json")
            
        middleware = ZstdMiddleware(get_response)
        
        request = self.factory.get("/", HTTP_ACCEPT_ENCODING="gzip, zstd")
        response = middleware(request)
        
        self.assertEqual(response.get("Content-Encoding"), "zstd")
        
        dctx = zstd.ZstdDecompressor()
        decompressed = dctx.decompress(response.content)
        self.assertEqual(decompressed, content)

    def test_zstd_middleware_ignores_small_responses(self):
        from django.http import HttpResponse
        from soroscan.middleware_zstd import ZstdMiddleware

        content = b"x" * 500
        def get_response(request):
            return HttpResponse(content, content_type="application/json")
            
        middleware = ZstdMiddleware(get_response)
        
        request = self.factory.get("/", HTTP_ACCEPT_ENCODING="gzip, zstd")
        response = middleware(request)
        
        self.assertNotEqual(response.get("Content-Encoding"), "zstd")
        self.assertEqual(response.content, content)
