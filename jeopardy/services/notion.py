import asyncio
import logging
import re

from notion_client import AsyncClient

from jeopardy.config import settings
from jeopardy.models.game import Clue

logger = logging.getLogger(__name__)

# Limit concurrent Notion API requests (rate limit: 3 req/s)
_semaphore = asyncio.Semaphore(3)


class NotionService:
    def __init__(self) -> None:
        self.client = AsyncClient(auth=settings.notion_api_key)

    async def fetch_clues(self) -> list[Clue]:
        """Query the Notion database and return all clues."""
        clues: list[Clue] = []
        has_more = True
        start_cursor = None

        while has_more:
            async with _semaphore:
                kwargs: dict = {"data_source_id": settings.notion_database_id}
                if start_cursor:
                    kwargs["start_cursor"] = start_cursor
                response = await self.client.data_sources.query(**kwargs)

            # Parse all pages in this batch concurrently (semaphore limits to 3 in-flight)
            tasks = [self._parse_page(page) for page in response["results"]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for page, result in zip(response["results"], results):
                if isinstance(result, Exception):
                    logger.exception("Failed to parse Notion page %s", page.get("id"), exc_info=result)
                elif result is not None:
                    clues.append(result)

            has_more = response.get("has_more", False)
            start_cursor = response.get("next_cursor")

        return clues

    async def _parse_page(self, page: dict) -> Clue | None:
        props = page["properties"]

        answer = self._extract_title(props)
        category = self._extract_select(props, "Category")
        dollar_value = self._extract_dollar_value(props)
        is_daily_double = self._extract_checkbox(props, "Daily Double")

        async with _semaphore:
            clue_text, clue_image_url = await self._get_page_content(page["id"])

        if not answer or not category or dollar_value is None:
            logger.warning(
                "Skipping incomplete page %s: answer=%r category=%r value=%r",
                page["id"],
                answer,
                category,
                dollar_value,
            )
            return None

        if not clue_text and not clue_image_url:
            logger.warning(
                "Skipping page %s with no text or image content: answer=%r",
                page["id"],
                answer,
            )
            return None

        return Clue(
            id=page["id"],
            answer=answer,
            clue_text=clue_text or "",
            clue_image_url=clue_image_url,
            category=category,
            dollar_value=dollar_value,
            is_daily_double=is_daily_double,
        )

    async def _get_page_content(self, page_id: str) -> tuple[str, str | None]:
        """Return (text_content, image_url) from page blocks."""
        blocks = await self.client.blocks.children.list(block_id=page_id)
        text_parts: list[str] = []
        image_url: str | None = None

        for block in blocks["results"]:
            block_type = block.get("type", "")

            if block_type in (
                "paragraph",
                "heading_1",
                "heading_2",
                "heading_3",
                "bulleted_list_item",
                "numbered_list_item",
            ):
                rich_texts = block.get(block_type, {}).get("rich_text", [])
                for rt in rich_texts:
                    text_parts.append(rt.get("plain_text", ""))

            elif block_type == "image" and image_url is None:
                img_data = block.get("image", {})
                img_type = img_data.get("type", "")
                if img_type == "file":
                    image_url = img_data.get("file", {}).get("url")
                elif img_type == "external":
                    image_url = img_data.get("external", {}).get("url")

        return " ".join(text_parts).strip(), image_url

    @staticmethod
    def _extract_title(props: dict) -> str | None:
        name_prop = props.get("Name", {})
        title_list = name_prop.get("title", [])
        if title_list:
            return title_list[0].get("plain_text", "").strip() or None
        return None

    @staticmethod
    def _extract_select(props: dict, prop_name: str) -> str | None:
        prop = props.get(prop_name, {})
        select = prop.get("select")
        if select:
            return select.get("name")
        return None

    @staticmethod
    def _extract_dollar_value(props: dict) -> int | None:
        prop = props.get("Dollar value", {})
        select = prop.get("select")
        if select:
            raw = select.get("name", "")
            digits = re.sub(r"[^\d]", "", raw)
            if digits:
                return int(digits)
        # Also try as a number property
        number = prop.get("number")
        if number is not None:
            return int(number)
        return None

    @staticmethod
    def _extract_checkbox(props: dict, prop_name: str) -> bool:
        prop = props.get(prop_name, {})
        return prop.get("checkbox", False)
