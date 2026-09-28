from django.test import TestCase
from soroscan.ingest.fields import CompressedJSONField

class CompressedJSONFieldTest(TestCase):
    def test_empty_dict_serialization(self):
        field = CompressedJSONField()
        
        empty_dict = {}
        
        # Test serialization
        compressed = field.get_prep_value(empty_dict)
        self.assertIsNotNone(compressed)
        self.assertNotEqual(compressed, b"{}")
        
        # Test deserialization
        deserialized = field.from_db_value(compressed, None, None)
        self.assertEqual(deserialized, empty_dict)
        
        # Test to_python
        to_python_val = field.to_python(compressed)
        self.assertEqual(to_python_val, empty_dict)
