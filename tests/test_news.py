from dipdash.data import parse_news

NEW = {"content": {"title": "Nested format", "provider": {"displayName": "Reuters"},
                   "canonicalUrl": {"url": "https://example.com/a"}}}
OLD = {"title": "Flat format", "publisher": "Motley Fool", "link": "https://example.com/b"}


def test_nested_and_flat_formats_give_the_same_shape():
    assert parse_news([NEW, OLD]) == [
        {"title": "Nested format", "src": "Reuters", "url": "https://example.com/a"},
        {"title": "Flat format", "src": "Motley Fool", "url": "https://example.com/b"}]


def test_items_without_a_title_are_dropped_and_missing_fields_become_empty_strings():
    assert parse_news([{"content": {"summary": "x"}}, {"title": "Only a title"}]) == [{"title": "Only a title", "src": "", "url": ""}]


def test_limit_applies_before_filtering_and_empty_input_is_fine():
    assert len(parse_news([OLD] * 9, limit=3)) == 3
    assert parse_news([]) == []


def test_click_through_url_is_used_when_there_is_no_canonical_one():
    n = {"content": {"title": "t", "clickThroughUrl": {"url": "https://example.com/c"}}}
    assert parse_news([n])[0]["url"] == "https://example.com/c"
