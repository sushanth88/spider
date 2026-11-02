import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import app
from database import Database


class TestVendorWebIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.temp_directory.name) / "vendors.db")
        self.previous_database_path = app.config["DATABASE_PATH"]
        app.config["DATABASE_PATH"] = self.database_path
        self.database = Database(self.database_path)
        self.nks_id = self.database.insert_product(
            "NKS Product",
            "/nks/1",
            source="NKS Distributors",
            supplier="Producer One",
        )
        self.standard_id = self.database.insert_product(
            "Standard Product",
            "/standard/1",
            source="Standard Distributing Company",
        )
        self.database.insert_price(self.nks_id, 10.0)
        self.database.insert_price(self.standard_id, 20.0)
        self.client = app.test_client()

    def tearDown(self):
        app.config["DATABASE_PATH"] = self.previous_database_path
        self.temp_directory.cleanup()

    def test_product_list_filters_by_distributor(self):
        response = self.client.get("/?source=NKS%20Distributors")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NKS Product", response.data)
        self.assertNotIn(b"Standard Product", response.data)

    def test_product_details_show_distributor_and_supplier(self):
        response = self.client.get(f"/product/{self.nks_id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NKS Distributors", response.data)
        self.assertIn(b"Producer One", response.data)

    def test_statistics_group_products_by_distributor(self):
        response = self.client.get("/stats")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"NKS Distributors", response.data)
        self.assertIn(b"Standard Distributing Company", response.data)

    def test_legacy_supplier_values_backfill_source(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy_path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(legacy_path)
            connection.execute(
                "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT, supplier TEXT, UNIQUE(name, url))"
            )
            connection.execute(
                "INSERT INTO products (name, url, supplier) VALUES (?, ?, ?)",
                ("Old NKS Product", "/legacy/nks", "NKS Distributors"),
            )
            connection.commit()
            connection.close()

            legacy_database = Database(str(legacy_path))
            product = legacy_database.get_product_by_id(1)

        self.assertEqual(product["source"], "NKS Distributors")


if __name__ == "__main__":
    unittest.main()