"""Tests for MCP tool manifest endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.api.mcp import _TOOLS

BASE = "http://test"


async def _get(path: str):
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE) as c:
        return await c.get(path)


# ── Manifest Endpoint Tests ────────────────────────────────────────────────────


class TestMCPManifest:
    @pytest.mark.asyncio
    async def test_manifest_returns_200(self):
        resp = await _get("/.well-known/mcp/tools")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_manifest_content_type_json(self):
        resp = await _get("/.well-known/mcp/tools")
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_manifest_has_schema_version(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        assert data["schema_version"] == "1.0"

    @pytest.mark.asyncio
    async def test_manifest_has_service_name(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        assert "WikiAura" in data["service"]

    @pytest.mark.asyncio
    async def test_manifest_has_tools_list(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        assert isinstance(data["tools"], list)
        assert len(data["tools"]) > 0

    @pytest.mark.asyncio
    async def test_manifest_tool_count_matches_definitions(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        assert len(data["tools"]) == len(_TOOLS)

    @pytest.mark.asyncio
    async def test_each_tool_has_required_fields(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        for tool in data["tools"]:
            assert "name" in tool, f"Tool missing 'name': {tool}"
            assert "description" in tool, f"Tool missing 'description': {tool}"
            assert "input_schema" in tool, f"Tool missing 'input_schema': {tool}"

    @pytest.mark.asyncio
    async def test_each_tool_input_schema_is_object(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        for tool in data["tools"]:
            schema = tool["input_schema"]
            assert schema["type"] == "object", f"Tool {tool['name']} schema type must be 'object'"
            assert "properties" in schema
            assert "required" in schema

    @pytest.mark.asyncio
    async def test_tool_names_are_unique(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        names = [t["name"] for t in data["tools"]]
        assert len(names) == len(set(names)), "Duplicate tool names found"

    @pytest.mark.asyncio
    async def test_analyze_trends_tool_present(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        names = [t["name"] for t in data["tools"]]
        assert "analyze_trends" in names

    @pytest.mark.asyncio
    async def test_analyze_trends_nl_tool_present(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        names = [t["name"] for t in data["tools"]]
        assert "analyze_trends_nl" in names

    @pytest.mark.asyncio
    async def test_generate_chart_tool_present(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        names = [t["name"] for t in data["tools"]]
        assert "generate_chart" in names

    @pytest.mark.asyncio
    async def test_generate_report_pdf_tool_present(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        names = [t["name"] for t in data["tools"]]
        assert "generate_report_pdf" in names

    @pytest.mark.asyncio
    async def test_cache_tools_present(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        names = [t["name"] for t in data["tools"]]
        assert "cache_stats" in names
        assert "cache_invalidate" in names


# ── analyze_trends Tool Schema Tests ──────────────────────────────────────────


class TestAnalyzeTrendsTool:
    async def _tool(self) -> dict:
        data = (await _get("/.well-known/mcp/tools")).json()
        return next(t for t in data["tools"] if t["name"] == "analyze_trends")

    @pytest.mark.asyncio
    async def test_topic_is_required(self):
        tool = await self._tool()
        assert "topic" in tool["input_schema"]["required"]

    @pytest.mark.asyncio
    async def test_language_codes_has_default(self):
        tool = await self._tool()
        props = tool["input_schema"]["properties"]
        assert "language_codes" in props
        assert props["language_codes"]["default"] == ["en"]

    @pytest.mark.asyncio
    async def test_granularity_has_enum(self):
        tool = await self._tool()
        props = tool["input_schema"]["properties"]
        assert "granularity" in props
        assert set(props["granularity"]["enum"]) == {"monthly", "daily"}

    @pytest.mark.asyncio
    async def test_include_ai_summary_is_optional(self):
        tool = await self._tool()
        assert "include_ai_summary" not in tool["input_schema"]["required"]

    @pytest.mark.asyncio
    async def test_topic_has_description(self):
        tool = await self._tool()
        desc = tool["input_schema"]["properties"]["topic"]["description"]
        assert len(desc) > 20


# ── Single Tool Endpoint Tests ─────────────────────────────────────────────────


class TestMCPSingleTool:
    @pytest.mark.asyncio
    async def test_get_analyze_trends_by_name(self):
        resp = await _get("/.well-known/mcp/tools/analyze_trends")
        assert resp.status_code == 200
        assert resp.json()["name"] == "analyze_trends"

    @pytest.mark.asyncio
    async def test_get_generate_chart_by_name(self):
        resp = await _get("/.well-known/mcp/tools/generate_chart")
        assert resp.status_code == 200
        assert resp.json()["name"] == "generate_chart"

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_404(self):
        resp = await _get("/.well-known/mcp/tools/does_not_exist")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_404_response_lists_available_tools(self):
        resp = await _get("/.well-known/mcp/tools/nonexistent")
        detail = resp.json()["detail"]
        assert "analyze_trends" in detail

    @pytest.mark.asyncio
    async def test_all_defined_tools_individually_retrievable(self):
        for tool in _TOOLS:
            resp = await _get(f"/.well-known/mcp/tools/{tool.name}")
            assert resp.status_code == 200, f"Failed for tool: {tool.name}"
            assert resp.json()["name"] == tool.name


# ── OpenAI / Anthropic Compatibility Tests ─────────────────────────────────────


class TestMCPCompatibility:
    @pytest.mark.asyncio
    async def test_anthropic_tool_use_format(self):
        """Verify manifest can be directly used as Anthropic tool_use tools list."""
        data = (await _get("/.well-known/mcp/tools")).json()
        for tool in data["tools"]:
            assert isinstance(tool["name"], str)
            assert isinstance(tool["description"], str)
            schema = tool["input_schema"]
            assert schema["type"] == "object"
            assert isinstance(schema["properties"], dict)
            assert isinstance(schema["required"], list)

    @pytest.mark.asyncio
    async def test_openai_function_call_format(self):
        """Verify tools are compatible with OpenAI function calling format."""
        data = (await _get("/.well-known/mcp/tools")).json()
        for tool in data["tools"]:
            assert " " not in tool["name"], f"Tool name must be snake_case: {tool['name']}"
            assert len(tool["description"]) >= 10

    @pytest.mark.asyncio
    async def test_tool_descriptions_mention_use_case(self):
        """Each tool description should indicate WHEN to use it."""
        data = (await _get("/.well-known/mcp/tools")).json()
        keywords = ["use", "when", "return", "generate", "parse", "analyze"]
        for tool in data["tools"]:
            desc_lower = tool["description"].lower()
            assert any(kw in desc_lower for kw in keywords), (
                f"Tool '{tool['name']}' description should indicate when/how to use it"
            )

    @pytest.mark.asyncio
    async def test_no_tool_has_empty_properties(self):
        """All required fields must exist in properties."""
        data = (await _get("/.well-known/mcp/tools")).json()
        for tool in data["tools"]:
            schema = tool["input_schema"]
            for req_field in schema["required"]:
                assert req_field in schema["properties"], (
                    f"Tool '{tool['name']}': required field '{req_field}' missing from properties"
                )

    @pytest.mark.asyncio
    async def test_manifest_base_url_present(self):
        data = (await _get("/.well-known/mcp/tools")).json()
        assert "base_url" in data
        assert data["base_url"].startswith("http")
