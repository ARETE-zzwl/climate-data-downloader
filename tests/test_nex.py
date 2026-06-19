import unittest

from cmip_downloader.models import DataQuery
from cmip_downloader.nex import parse_listing


LISTING = """<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <IsTruncated>false</IsTruncated>
  <Contents><Key>NEX-GDDP-CMIP6/ACCESS-CM2/historical/r1i1p1f1/pr/pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_1999_v2.0.nc</Key><ETag>&quot;a-2&quot;</ETag><Size>90</Size></Contents>
  <Contents><Key>NEX-GDDP-CMIP6/ACCESS-CM2/historical/r1i1p1f1/pr/pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2000.nc</Key><ETag>&quot;b-2&quot;</ETag><Size>100</Size></Contents>
  <Contents><Key>NEX-GDDP-CMIP6/ACCESS-CM2/historical/r1i1p1f1/pr/pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2000_v1.1.nc</Key><ETag>&quot;c-2&quot;</ETag><Size>110</Size></Contents>
  <Contents><Key>NEX-GDDP-CMIP6/ACCESS-CM2/historical/r1i1p1f1/pr/pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2000_v2.0.nc</Key><ETag>&quot;d-2&quot;</ETag><Size>120</Size></Contents>
  <Contents><Key>NEX-GDDP-CMIP6/ACCESS-CM2/historical/r1i1p1f1/pr/pr_day_ACCESS-CM2_historical_r1i1p1f1_gn_2001_v2.0.nc</Key><ETag>&quot;e-2&quot;</ETag><Size>130</Size></Contents>
</ListBucketResult>"""


class NexListingTests(unittest.TestCase):
    def test_selects_requested_years_and_v2_by_default(self):
        query = DataQuery("ACCESS-CM2", "historical", "r1i1p1f1", "pr", 2000, 2001)

        items, token = parse_listing(LISTING, query)

        self.assertIsNone(token)
        self.assertEqual([item.size for item in items], [120, 130])
        self.assertTrue(all(item.filename.endswith("_v2.0.nc") for item in items))


if __name__ == "__main__":
    unittest.main()

