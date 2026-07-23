import json
from pathlib import Path
import pytest
from app.rag.parse.mineru_adapter import parse_mineru_output


def test_mineru_rejects_non_list_json(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为空时，抛出ValueError
    """
    content_file = tmp_path / "sample_content_list.json"
    content_file.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        parse_mineru_output(str(tmp_path), "dummy.pdf")


def test_mineru_rejects_unknown_type(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为unknown_type时，抛出ValueError
    """
    content_file = tmp_path / "unknown_type_content_list.json"
    content_file.write_text('[{"type":"image","text":"图表内容","page_idx":0}]', encoding="utf-8")

    with pytest.raises(ValueError):
        parse_mineru_output(str(tmp_path), "dummy.pdf")


def test_mineru_preserves_title_hierarchy(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为title_content_list时，返回的result为3个title
    """
    content_file = tmp_path / "title_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"公司概况","text_level":1,"page_idx":0},{"type":"text","text":"主要业务","text_level":2,"page_idx":0},{"type":"text","text":"公司主要从事……","text_level":null,"page_idx":0}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result) == 3
    assert [chunk.type for chunk in result] == ["title", "title", "paragraph"]


def test_mineru_propagates_section_hierarchy(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为title_content_list时，返回的result的section为公司概况/主要业务
    """
    content_file = tmp_path / "title_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"公司概况","text_level":1,"page_idx":0},{"type":"text","text":"主要业务","text_level":2,"page_idx":0},{"type":"text","text":"公司主要从事……","text_level":null,"page_idx":0}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert [chunk.section for chunk in result] == [
        "公司概况",
        "公司概况/主要业务",
        "公司概况/主要业务",
    ]


def test_mineru_table_body_is_searchable(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为table_content_list时，返回的result的table_body为利润明细表
    """
    table_body = "| 项目 | 金额 | | 净利润专属项 | 98765 |"
    content_file = tmp_path / "table_content_list.json"
    tmp_json = json.dumps([{"type":"table","table_caption":["利润明细表"],"table_body":table_body,"page_idx":0}], ensure_ascii=False)
    content_file.write_text(
        tmp_json,
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result) == 1
    assert result[0].type == "table"
    assert "净利润专属项" in result[0].text
    assert "98765" in result[0].text
    assert result[0].table_md == table_body
    assert result[0].page == 1


def test_mineru_preserves_mixed_element_order(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为table_caption_content_list时，返回的result为3个元素，分别是text、table、text
    """
    content_file = tmp_path / "table_caption_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"顺序A","page_idx":0},{"type":"table","table_caption":["顺序B"],"table_body":"表体专属B","page_idx":0},{"type":"text","text":"顺序C","page_idx":0}]',
        encoding="utf-8",
    )
    result = parse_mineru_output(str(tmp_path), "dummy.pdf")
    assert len(result) == 3
    assert [chunk.type for chunk in result] == ["paragraph", "table", "paragraph"]
    assert result[0].text == "顺序A"
    assert result[1].table_md is not None and "表体专属B" in result[1].table_md
    assert result[2].text == "顺序C"


def test_mineru_rejects_missing_page_idx(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为missing_page_idx_content_list时，抛出ValueError
    """
    content_file = tmp_path / "missing_page_idx_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"缺页码正文","text_level":null}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        parse_mineru_output(str(tmp_path), "dummy.pdf")

def test_mineru_rejects_empty_title(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为empty_title_content_list时，抛出ValueError
    """
    content_file = tmp_path / "empty_title_content_list.json"
    content_file.write_text(
        '[{"type":"text","text":"","text_level":1,"page_idx":0}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        parse_mineru_output(str(tmp_path), "dummy.pdf")

def test_mineru_rejects_empty_table_body(tmp_path: Path):
    """
    测试parse_mineru_output函数，当content_file为empty_table_body_content_list时，抛出ValueError
    """
    content_file = tmp_path / "empty_table_body_content_list.json"
    content_file.write_text(
        '[{"type":"table","table_caption":["空表测试"],"table_body":"","page_idx":0}]',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        parse_mineru_output(str(tmp_path), "dummy.pdf")