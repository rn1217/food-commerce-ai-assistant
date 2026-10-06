import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.init_products import ROOT, load_products, insert_products


class ProductImportTests(unittest.TestCase):
    def setUp(self):
        self.frame = load_products(ROOT / 'data' / 'products.csv')

    def test_catalog_has_30_unique_valid_products(self):
        self.assertEqual(len(self.frame), 30)
        self.assertEqual(self.frame.product_id.nunique(), 30)

    def test_bad_values_and_duplicate_ids_are_rejected_before_db(self):
        cases = [('price', '-1'), ('price', '20000.5'), ('price', 'NaN'),
                 ('name', '  '), ('sweetness', '6'), ('packaging', 'box'),
                 ('storage_method', 'hot'), ('gift_available', 'true'), ('product_id', '2')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'products.csv'
            for column, value in cases:
                with self.subTest(column=column, value=value):
                    frame = self.frame.astype(str)
                    frame.loc[0, column] = value
                    frame.to_csv(path, index=False)
                    with self.assertRaises(ValueError):
                        load_products(path)

    def connection(self, existing):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = existing
        return connection, cursor

    def test_repeat_import_skips_all_existing_rows(self):
        connection, cursor = self.connection(self.frame.to_dict(orient='records'))
        with patch('scripts.init_products.get_connection') as connect:
            connect.return_value.__enter__.return_value = connection
            self.assertEqual(insert_products(self.frame), {'added': 0, 'skipped': 30})
        cursor.executemany.assert_not_called()

    def test_conflict_aborts_without_overwriting(self):
        existing = self.frame.to_dict(orient='records')
        existing[0]['price'] = 1
        connection, cursor = self.connection(existing)
        with patch('scripts.init_products.get_connection') as connect:
            connect.return_value.__enter__.return_value = connection
            with self.assertRaises(ValueError):
                insert_products(self.frame)
        cursor.executemany.assert_not_called()
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()

    def test_insert_failure_rolls_back(self):
        connection, cursor = self.connection([])
        cursor.executemany.side_effect = RuntimeError('simulated failure')
        with patch('scripts.init_products.get_connection') as connect:
            connect.return_value.__enter__.return_value = connection
            with self.assertRaises(RuntimeError):
                insert_products(self.frame)
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()


if __name__ == '__main__':
    unittest.main()
