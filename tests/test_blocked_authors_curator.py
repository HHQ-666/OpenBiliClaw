from pathlib import Path
from tempfile import mkdtemp

from openbiliclaw.discovery.engine import DiscoveredContent
from openbiliclaw.recommendation.curator import PoolCurator
from openbiliclaw.storage.database import Database


def test_curator_filters_blocked_authors() -> None:
    tmp = Path(mkdtemp())
    db = Database(tmp / "curator_test.db")
    db.initialize()

    # Add blocked author for bilibili and global
    db.add_blocked_author("营销号A", source_platform="bilibili")
    db.add_blocked_author("水军B", source_platform="")

    curator = PoolCurator(database=db)

    c1 = DiscoveredContent(
        bvid="BV1",
        title="正常优质视频",
        author_name="优质创作者",
        source_platform="bilibili",
    )
    c2 = DiscoveredContent(
        bvid="BV2",
        title="劣质视频A",
        author_name="营销号A",
        source_platform="bilibili",
    )
    c3 = DiscoveredContent(
        bvid="BV3",
        title="劣质推文B",
        author_name="水军B",
        source_platform="twitter",
    )
    c4 = DiscoveredContent(
        bvid="BV4",
        title="同名其它平台A",
        author_name="营销号A",
        source_platform="youtube",
    )

    eligible = curator.filter_candidates_for_serving([c1, c2, c3, c4])

    # c2 (bilibili 营销号A) and c3 (global 水军B) must be filtered out
    # c1 (优质创作者) and c4 (youtube 营销号A, blocked only on bilibili) should survive
    eligible_bvids = {item.bvid for item in eligible}
    assert "BV1" in eligible_bvids
    assert "BV4" in eligible_bvids
    assert "BV2" not in eligible_bvids
    assert "BV3" not in eligible_bvids
