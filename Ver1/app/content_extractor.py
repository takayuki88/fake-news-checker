import re
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from .config import Settings
from .models import ResolvedPage
from .time_utils import build_analysis_timestamp_fields

PRIMARY_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    ".article-body",
    ".articleBody",
    ".article__body",
    ".entry-content",
    ".entry-body",
    ".post-content",
    ".post__content",
    ".news-body",
    ".story-body",
]
SECONDARY_SELECTORS = [
    ".content",
    ".content-body",
    ".main-content",
    ".article",
    ".story",
    ".post",
]
NOISE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "nav",
    "footer",
    "header",
    "aside",
    "form",
    "button",
    ".related",
    ".recommend",
    ".ranking",
    ".sns-share",
    ".social-share",
    ".breadcrumb",
]
AUTHOR_META_KEYS = [
    "author",
    "article:author",
]
AUTHOR_SELECTORS = [
    "[rel='author']",
    ".author",
    ".byline",
    ".article-author",
    ".post-author",
    ".writer",
]
PUBLISHED_META_KEYS = [
    "article:published_time",
    "og:published_time",
    "pubdate",
    "date",
]
DATE_SELECTORS = [
    "time[datetime]",
    "time",
    ".date",
    ".published",
    ".publish-date",
    ".article-date",
    ".entry-date",
]
URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")
CONFIRMED_BLOCKED_DOMAIN_SUFFIXES = [
    "x.com",
    "twitter.com",
    "instagram.com",
    "facebook.com",
    "fb.com",
    "threads.net",
    "linkedin.com",
    "reddit.com",
    "discord.com",
    "discord.gg",
    "open.spotify.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "twitch.tv",
    "tumblr.com",
    "snapchat.com",
]
PROVISIONALLY_BLOCKED_DOMAIN_SUFFIXES = [
]
ROBOTS_ONLY_DOMAIN_SUFFIXES = [
    "bsky.app",
    "pinterest.com",
    "medium.com",
    "substack.com",
    "line.me",
    "note.com",
    "nicovideo.jp",
    "nico.ms",
]
BLOCKED_DOMAIN_SUFFIXES = CONFIRMED_BLOCKED_DOMAIN_SUFFIXES + PROVISIONALLY_BLOCKED_DOMAIN_SUFFIXES
MANUAL_PASTE_MESSAGE = "閲覧サイト側の規約や取得制限により、本文を貼り付けて判定してください。"
ROBOTS_UNCERTAIN_MESSAGE = "このサイトは取得可否を自動確認できないため、安全のため本文を貼り付けて判定してください。"
POLICY_RESEARCH_MESSAGE = "閲覧サイト側の規約や取得制限を自動確認した結果、本文を貼り付けて判定してください。"
POLICY_CACHE_TTL_SECONDS = 60 * 60 * 24
POLICY_FETCH_LIMIT = 6
LEGAL_PATH_CANDIDATES = [
    "/terms",
    "/terms/",
    "/terms-of-service",
    "/terms-of-use",
    "/legal",
    "/legal/",
    "/tos",
    "/about/terms",
    "/about/legal",
    "/利用規約",
]
LEGAL_LINK_PATTERNS = [
    "terms",
    "legal",
    "tos",
    "conditions",
    "利用規約",
    "利用条件",
    "規約",
]
AUTOMATION_TERMS = [
    "scrap",
    "crawler",
    "spider",
    "robot",
    "bot",
    "data mining",
    "automated",
    "クローラ",
    "クローラー",
    "ロボット",
    "スクレイ",
    "自動取得",
    "自動収集",
    "自動アクセス",
    "自動巡回",
]
PROHIBITION_TERMS = [
    "prohibit",
    "prohibited",
    "must not",
    "may not",
    "not allow",
    "without prior written consent",
    "without written consent",
    "forbid",
    "forbidden",
    "禁止",
    "してはなら",
    "できません",
    "許可なく",
    "許諾なく",
    "禁じ",
]
DOMAIN_POLICY_CACHE: dict[str, tuple[float, bool, str | None, str | None, str | None, str | None, tuple[str, ...]]] = {}
COMMON_SECOND_LEVEL_SUFFIXES = {
    "co.jp",
    "or.jp",
    "ne.jp",
    "ac.jp",
    "go.jp",
    "ed.jp",
    "gr.jp",
    "lg.jp",
    "co.uk",
    "org.uk",
    "ac.uk",
}


def normalize_whitespace(value: str) -> str:
    return " ".join(value.replace("\u3000", " ").split())


def limit_text(value: str, max_chars: int) -> str:
    return value[:max_chars].strip()


def clamp(value: int, lower: int = 0, upper: int = 100) -> int:
    return max(lower, min(upper, value))


def normalize_hostname(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return (parsed.hostname or "").lower()


def is_blocked_domain(hostname: str) -> bool:
    return any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in BLOCKED_DOMAIN_SUFFIXES)


def is_known_policy_domain(hostname: str) -> bool:
    known_suffixes = BLOCKED_DOMAIN_SUFFIXES + ROBOTS_ONLY_DOMAIN_SUFFIXES
    return any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in known_suffixes)


def registered_domain(hostname: str) -> str:
    parts = [part for part in hostname.split(".") if part]
    if len(parts) <= 2:
        return hostname
    last_two = ".".join(parts[-2:])
    if last_two in COMMON_SECOND_LEVEL_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


def brand_tokens(hostname: str) -> list[str]:
    domain = registered_domain(hostname)
    tokens = re.split(r"[^a-z0-9]+", domain.lower())
    return [token for token in tokens if len(token) >= 4 and token not in {"www", "help", "legal", "terms"}]


def is_related_policy_host(expected_hostname: str, candidate_hostname: str) -> bool:
    if not expected_hostname or not candidate_hostname:
        return False
    if candidate_hostname == expected_hostname:
        return True
    if registered_domain(candidate_hostname) == registered_domain(expected_hostname):
        return True
    expected_tokens = brand_tokens(expected_hostname)
    if expected_tokens and any(token in candidate_hostname for token in expected_tokens):
        return True
    candidate_tokens = brand_tokens(candidate_hostname)
    if candidate_tokens and any(token in expected_hostname for token in candidate_tokens):
        return True
    return False


def build_robots_url(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def build_url_path_for_robots(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path


def strip_robots_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def parse_robots_groups(robots_text: str) -> list[tuple[list[str], list[tuple[str, str]]]]:
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    current_agents: list[str] = []
    current_rules: list[tuple[str, str]] = []

    for raw_line in robots_text.splitlines():
        line = strip_robots_comment(raw_line)
        if not line or ":" not in line:
            continue
        field, value = line.split(":", 1)
        field = field.strip().lower()
        value = value.strip()

        if field == "user-agent":
            if current_agents and current_rules:
                groups.append((current_agents, current_rules))
                current_agents = []
                current_rules = []
            current_agents.append(value.lower())
            continue

        if field in {"allow", "disallow"} and current_agents:
            current_rules.append((field, value))

    if current_agents:
        groups.append((current_agents, current_rules))

    return groups


def select_robots_rules(robots_text: str, user_agent: str) -> list[tuple[str, str]]:
    groups = parse_robots_groups(robots_text)
    lowered_agent = user_agent.lower()
    exact_or_partial: list[tuple[str, str]] = []
    wildcard: list[tuple[str, str]] = []

    for agents, rules in groups:
        if any(agent != "*" and agent in lowered_agent for agent in agents):
            exact_or_partial.extend(rules)
        elif any(agent == "*" for agent in agents):
            wildcard.extend(rules)

    return exact_or_partial or wildcard


def robots_disallow_path(robots_text: str, path: str, user_agent: str) -> bool:
    rules = select_robots_rules(robots_text, user_agent)
    best_match_length = -1
    best_is_disallow = False

    for directive, rule_path in rules:
        if directive == "disallow" and rule_path == "":
            continue
        if not path.startswith(rule_path):
            continue
        rule_length = len(rule_path)
        is_disallow = directive == "disallow"
        if rule_length > best_match_length or (rule_length == best_match_length and not is_disallow):
            best_match_length = rule_length
            best_is_disallow = is_disallow

    return best_match_length >= 0 and best_is_disallow


def is_canonical_robots_response(response: httpx.Response, expected_hostname: str) -> bool:
    response_hostname = normalize_hostname(str(response.url))
    response_path = response.url.path.rstrip("/") or "/"
    return response_hostname == expected_hostname and response_path == "/robots.txt"


def get_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def get_cached_policy_result(hostname: str) -> tuple[bool, str | None, str | None, str | None, str | None, list[str]] | None:
    cached = DOMAIN_POLICY_CACHE.get(hostname)
    if not cached:
        return None
    expires_at, allowed, message, status, note, checked_url, checked_urls = cached
    if expires_at < time.time():
        DOMAIN_POLICY_CACHE.pop(hostname, None)
        return None
    return allowed, message, status, note, checked_url, list(checked_urls)


def set_cached_policy_result(
    hostname: str,
    allowed: bool,
    message: str | None,
    status: str | None,
    note: str | None,
    checked_url: str | None,
    checked_urls: list[str] | tuple[str, ...],
) -> None:
    DOMAIN_POLICY_CACHE[hostname] = (
        time.time() + POLICY_CACHE_TTL_SECONDS,
        allowed,
        message,
        status,
        note,
        checked_url,
        tuple(checked_urls),
    )


async def resolve_final_url(url: str, client: httpx.AsyncClient, settings: Settings) -> str | None:
    headers = {
        "User-Agent": settings.request_user_agent,
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        async with client.stream("GET", url, headers=headers) as response:
            return str(response.url)
    except httpx.HTTPError:
        return None


async def fetch_robots_text(
    url: str,
    expected_hostname: str,
    client: httpx.AsyncClient,
    settings: Settings,
) -> tuple[str | None, str | None, bool]:
    headers = {"User-Agent": settings.robots_user_agent}
    robots_url = build_robots_url(url)

    try:
        response = await client.get(robots_url, headers=headers)
    except httpx.HTTPError:
        return None, ROBOTS_UNCERTAIN_MESSAGE, False

    if response.status_code in {401, 403, 429}:
        return None, MANUAL_PASTE_MESSAGE, False
    if response.status_code in {404, 410}:
        return "", None, True
    if response.status_code >= 500:
        return None, ROBOTS_UNCERTAIN_MESSAGE, False
    if response.status_code != 200:
        return "", None, True
    if not is_canonical_robots_response(response, expected_hostname):
        return None, None, False
    return response.text, None, True


async def fetch_html_document(
    url: str,
    client: httpx.AsyncClient,
    settings: Settings,
) -> tuple[str | None, str | None]:
    headers = {
        "User-Agent": settings.request_user_agent,
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        response = await client.get(url, headers=headers)
    except httpx.HTTPError:
        return None, None
    if response.status_code != 200:
        return None, str(response.url)
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        return None, str(response.url)
    return response.text, str(response.url)


def is_legal_link(text: str, href: str) -> bool:
    target = f"{text} {href}".lower()
    return any(keyword in target for keyword in LEGAL_LINK_PATTERNS)


def normalize_policy_url(base_url: str, href: str) -> str | None:
    absolute_url = urljoin(base_url, href.strip())
    parsed = urlparse(absolute_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return absolute_url


def collect_policy_links_from_html(html: str, base_url: str, expected_hostname: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        text = normalize_whitespace(anchor.get_text(" ", strip=True))
        if not href or not is_legal_link(text, href):
            continue
        absolute_url = normalize_policy_url(base_url, href)
        if not absolute_url:
            continue
        candidate_hostname = normalize_hostname(absolute_url)
        if not is_related_policy_host(expected_hostname, candidate_hostname):
            continue
        candidates.append(absolute_url)
    return list(dict.fromkeys(candidates))


def build_policy_candidates(seed_url: str, expected_hostname: str, html_documents: list[tuple[str, str]]) -> list[str]:
    origin = get_origin(seed_url)
    candidates = [urljoin(origin, path) for path in LEGAL_PATH_CANDIDATES]
    for html, base_url in html_documents:
        candidates.extend(collect_policy_links_from_html(html, base_url, expected_hostname))
    deduped = list(dict.fromkeys(candidates))
    return deduped[:POLICY_FETCH_LIMIT]


def extract_policy_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in ["script", "style", "noscript", "svg"]:
        for node in soup.select(selector):
            node.decompose()
    text = normalize_whitespace(soup.get_text(" ", strip=True)).lower()
    return limit_text(text, 30000)


def contains_scraping_prohibition(policy_text: str) -> bool:
    has_automation_term = any(term in policy_text for term in AUTOMATION_TERMS)
    has_prohibition_term = any(term in policy_text for term in PROHIBITION_TERMS)
    return has_automation_term and has_prohibition_term


async def research_unknown_domain_policy(
    requested_url: str,
    resolved_url: str | None,
    client: httpx.AsyncClient,
    settings: Settings,
) -> tuple[bool, str | None, str | None, str | None, str | None, list[str]]:
    policy_url = resolved_url or requested_url
    hostname = normalize_hostname(policy_url)
    if not hostname or is_known_policy_domain(hostname):
        return True, None, None, None, None, []

    cached = get_cached_policy_result(hostname)
    if cached:
        return cached

    seed_urls = [policy_url]
    homepage_url = get_origin(policy_url)
    if homepage_url != policy_url:
        seed_urls.append(homepage_url)

    html_documents: list[tuple[str, str]] = []
    for seed in seed_urls:
        html, final_seed_url = await fetch_html_document(seed, client, settings)
        if html and final_seed_url and is_related_policy_host(hostname, normalize_hostname(final_seed_url)):
            html_documents.append((html, final_seed_url))

    candidate_urls = build_policy_candidates(policy_url, hostname, html_documents)
    reviewed_count = 0
    reviewed_url: str | None = None
    reviewed_urls: list[str] = []
    for candidate_url in candidate_urls:
        html, final_candidate_url = await fetch_html_document(candidate_url, client, settings)
        if not html or not final_candidate_url:
            continue
        if not is_related_policy_host(hostname, normalize_hostname(final_candidate_url)):
            continue
        reviewed_count += 1
        reviewed_url = final_candidate_url
        if final_candidate_url not in reviewed_urls:
            reviewed_urls.append(final_candidate_url)
        if contains_scraping_prohibition(extract_policy_text(html)):
            result = (
                False,
                POLICY_RESEARCH_MESSAGE,
                "規約確認で禁止表現を検出",
                "新規ドメインの規約候補ページを確認し、自動取得の禁止表現を検出しました。",
                final_candidate_url,
                reviewed_urls,
            )
            set_cached_policy_result(hostname, *result)
            return result

    if reviewed_count > 0:
        result = (
            True,
            None,
            "規約候補ページを確認",
            "新規ドメインの規約候補ページを自動確認し、明確な自動取得禁止表現は検出されませんでした。",
            reviewed_url,
            reviewed_urls,
        )
        set_cached_policy_result(hostname, *result)
        return result

    result = (
        True,
        None,
        "robots.txt優先",
        "新規ドメインの規約候補ページは十分に特定できなかったため、robots.txt を優先して判定しました。",
        None,
        [],
    )
    set_cached_policy_result(hostname, *result)
    return result


def get_meta_content(soup: BeautifulSoup, *keys: str) -> str:
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return normalize_whitespace(tag["content"])
    return ""


def find_first_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = normalize_whitespace(node.get_text(" ", strip=True))
            if text:
                return text
    return ""


def infer_title(soup: BeautifulSoup) -> str:
    if title := get_meta_content(soup, "og:title", "twitter:title"):
        return title
    if soup.title:
        return normalize_whitespace(soup.title.get_text(" ", strip=True))
    h1 = soup.find("h1")
    if h1:
        return normalize_whitespace(h1.get_text(" ", strip=True))
    return ""


def infer_site_name(soup: BeautifulSoup, url: str | None) -> str:
    if site_name := get_meta_content(soup, "og:site_name", "application-name"):
        return site_name
    if url:
        return urlparse(url).netloc.replace("www.", "")
    return "manual"


def infer_author_name(soup: BeautifulSoup) -> str | None:
    author = get_meta_content(soup, *AUTHOR_META_KEYS) or find_first_text(soup, AUTHOR_SELECTORS)
    return author or None


def infer_published_at(soup: BeautifulSoup) -> str | None:
    if published := get_meta_content(soup, *PUBLISHED_META_KEYS):
        return published

    for selector in DATE_SELECTORS:
        node = soup.select_one(selector)
        if not node:
            continue
        if node.get("datetime"):
            return normalize_whitespace(str(node["datetime"]))
        text = normalize_whitespace(node.get_text(" ", strip=True))
        if text:
            return text
    return None


def extract_text_chunks(node: Tag) -> tuple[list[str], int, int]:
    paragraph_count = 0
    heading_count = 0
    chunks: list[str] = []

    for element in node.select("h1, h2, h3, p, li, blockquote"):
        text = normalize_whitespace(element.get_text(" ", strip=True))
        if not text:
            continue
        if element.name in {"h1", "h2", "h3"}:
            heading_count += 1
        if element.name in {"p", "li", "blockquote"}:
            paragraph_count += 1
        if len(text) >= 20:
            chunks.append(text)

    deduped = list(dict.fromkeys(chunks))
    return deduped, paragraph_count, heading_count


def extract_reference_links(node: Tag) -> list[str]:
    links: list[str] = []
    for anchor in node.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if href.startswith("http://") or href.startswith("https://"):
            links.append(href)
    return list(dict.fromkeys(links))


def sentence_count(text: str) -> int:
    return max(1, sum(text.count(mark) for mark in ["。", ".", "!", "！", "?", "？"]))


def score_candidate(text: str, paragraph_count: int, heading_count: int, reference_link_count: int, selector_weight: int) -> int:
    text_length = len(text)
    avg_chunk_length = text_length / max(paragraph_count, 1)
    punctuation_ratio = sentence_count(text) / max(text_length, 1)

    score = min(text_length // 10, 360)
    score += paragraph_count * 18
    score += heading_count * 12
    score += min(reference_link_count * 16, 64)
    score += selector_weight

    if 35 <= avg_chunk_length <= 280:
        score += 45
    else:
        score -= 18

    if 0.004 <= punctuation_ratio <= 0.05:
        score += 55
    else:
        score -= 24

    return max(score, 0)


def build_candidate(node: Tag, label: str, selector_weight: int) -> dict | None:
    chunks, paragraph_count, heading_count = extract_text_chunks(node)
    if not chunks:
        return None

    text = "\n".join(chunks)
    if len(text) < 80:
        return None

    reference_links = extract_reference_links(node)
    score = score_candidate(text, paragraph_count, heading_count, len(reference_links), selector_weight)
    return {
        "label": label,
        "text": text,
        "paragraph_count": paragraph_count,
        "heading_count": heading_count,
        "reference_link_count": len(reference_links),
        "score": score,
    }


def collect_candidates(soup: BeautifulSoup) -> list[dict]:
    candidates: list[dict] = []

    for selector in PRIMARY_SELECTORS:
        for node in soup.select(selector):
            candidate = build_candidate(node, f"primary:{selector}", 80)
            if candidate:
                candidates.append(candidate)

    for selector in SECONDARY_SELECTORS:
        for node in soup.select(selector):
            candidate = build_candidate(node, f"secondary:{selector}", 35)
            if candidate:
                candidates.append(candidate)

    body = soup.body or soup
    fallback = build_candidate(body, "fallback:body", 10)
    if fallback:
        candidates.append(fallback)

    unique_by_text: dict[str, dict] = {}
    for candidate in candidates:
        key = candidate["text"]
        if key not in unique_by_text or unique_by_text[key]["score"] < candidate["score"]:
            unique_by_text[key] = candidate

    return sorted(unique_by_text.values(), key=lambda item: item["score"], reverse=True)


def build_preview(text: str) -> str:
    return limit_text(text.replace("\n", " "), 320)


def manual_reference_link_count(text: str) -> int:
    return len(dict.fromkeys(URL_PATTERN.findall(text)))


async def is_url_fetch_allowed(
    url: str,
    settings: Settings,
) -> tuple[bool, str | None, str | None, str | None, str | None, list[str]]:
    hostname = normalize_hostname(url)
    if not hostname:
        return False, "URLを正しく解釈できませんでした。ページ本文を貼り付けて判定してください。", None, None, None, []

    if is_blocked_domain(hostname):
        return False, MANUAL_PASTE_MESSAGE, None, None, None, []

    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout_seconds,
        follow_redirects=True,
    ) as client:
        resolved_url = await resolve_final_url(url, client, settings)
        resolved_hostname = normalize_hostname(resolved_url)
        if resolved_hostname and resolved_hostname != hostname and is_blocked_domain(resolved_hostname):
            return False, MANUAL_PASTE_MESSAGE, None, None, None, []

        original_robots_text, message, original_robots_usable = await fetch_robots_text(
            url,
            hostname,
            client,
            settings,
        )
        if message:
            return False, message, None, None, None, []
        if original_robots_usable and original_robots_text:
            if robots_disallow_path(original_robots_text, build_url_path_for_robots(url), settings.robots_user_agent):
                return False, MANUAL_PASTE_MESSAGE, None, None, None, []

        policy_url = resolved_url or url
        policy_hostname = normalize_hostname(policy_url) or hostname
        policy_path = build_url_path_for_robots(policy_url)

        if policy_hostname != hostname:
            resolved_robots_text, message, resolved_robots_usable = await fetch_robots_text(
                policy_url,
                policy_hostname,
                client,
                settings,
            )
            if message:
                return False, message, None, None, None, []
            if not resolved_robots_usable:
                return False, ROBOTS_UNCERTAIN_MESSAGE, None, None, None, []
            if resolved_robots_text and robots_disallow_path(resolved_robots_text, policy_path, settings.robots_user_agent):
                return False, MANUAL_PASTE_MESSAGE, None, None, None, []
            policy_allowed, policy_message, policy_status, policy_note, policy_check_url, policy_checked_urls = await research_unknown_domain_policy(
                url,
                resolved_url,
                client,
                settings,
            )
            return policy_allowed, policy_message, policy_status, policy_note, policy_check_url, policy_checked_urls

        if original_robots_usable:
            if original_robots_text and policy_url != url:
                if robots_disallow_path(original_robots_text, policy_path, settings.robots_user_agent):
                    return False, MANUAL_PASTE_MESSAGE, None, None, None, []
            policy_allowed, policy_message, policy_status, policy_note, policy_check_url, policy_checked_urls = await research_unknown_domain_policy(
                url,
                resolved_url,
                client,
                settings,
            )
            return policy_allowed, policy_message, policy_status, policy_note, policy_check_url, policy_checked_urls

    return False, ROBOTS_UNCERTAIN_MESSAGE, None, None, None, []


async def fetch_page_html(url: str, settings: Settings) -> tuple[str, str]:
    headers = {
        "User-Agent": settings.request_user_agent,
        "Accept": "text/html,application/xhtml+xml",
    }
    async with httpx.AsyncClient(
        timeout=settings.fetch_timeout_seconds,
        follow_redirects=True,
    ) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
            raise ValueError("HTMLページではないため本文抽出できませんでした。")
        return response.text, str(response.url)


def parse_html_to_page(
    html: str,
    url: str,
    settings: Settings,
    requested_url: str | None = None,
    policy_status: str | None = None,
    policy_note: str | None = None,
    policy_check_url: str | None = None,
    policy_checked_urls: list[str] | None = None,
) -> ResolvedPage:
    soup = BeautifulSoup(html, "html.parser")
    timestamp_fields = build_analysis_timestamp_fields(settings)

    for selector in NOISE_SELECTORS:
        for node in soup.select(selector):
            node.decompose()

    candidates = collect_candidates(soup)
    if not candidates:
        raise ValueError("ページ本文を十分に抽出できませんでした。本文を手入力してください。")

    best = candidates[0]
    analysis_text = limit_text(best["text"], settings.max_fetch_chars)
    if len(analysis_text) < settings.min_auto_extract_chars:
        raise ValueError("ページ本文が短すぎるため、自動抽出では判定しにくいページです。本文を手入力してください。")

    title = infer_title(soup) or "タイトル未取得"
    description = get_meta_content(soup, "description", "og:description", "twitter:description")
    if description:
        analysis_text = limit_text(f"{title}\n{description}\n{analysis_text}", settings.max_fetch_chars)

    author_name = infer_author_name(soup)
    published_at = infer_published_at(soup)
    extraction_score = clamp(best["score"] // 7)
    redirect_note = ""
    if requested_url and requested_url != url:
        redirect_note = f" 入力URLは短縮URLまたは転送URLで、最終的に {normalize_hostname(url)} のページを対象にしました。"
    note = (
        "URLから本文を自動抽出しました。"
        f"{redirect_note}"
        f" 候補 {best['label']} を採用し、抽出品質は {extraction_score}/100 です。"
        " JavaScript描画や会員限定記事では一部しか取れない場合があります。"
    )
    if policy_note:
        note = f"{note} {policy_note}"

    return ResolvedPage(
        title=title,
        site_name=infer_site_name(soup, url),
        source_url=url,
        input_source="page_url",
        extraction_note=note,
        analysis_date=timestamp_fields["analysis_date"],
        analysis_datetime=timestamp_fields["analysis_datetime"],
        analysis_timezone=timestamp_fields["analysis_timezone"],
        policy_check_status=policy_status,
        policy_check_note=policy_note,
        policy_check_url=policy_check_url,
        policy_checked_urls=policy_checked_urls or [],
        text_preview=build_preview(analysis_text),
        extracted_chars=len(analysis_text),
        has_author=bool(author_name),
        has_published_at=bool(published_at),
        author_name=author_name,
        published_at=published_at,
        reference_link_count=best["reference_link_count"],
        paragraph_count=best["paragraph_count"],
        heading_count=best["heading_count"],
        extraction_score=extraction_score,
        analysis_text=analysis_text,
    )


def pseudo_title_from_text(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return limit_text(first_line or "手入力テキスト", 80)


def estimate_manual_paragraph_count(text: str) -> int:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines:
        return len(lines)
    return max(1, sentence_count(text) // 2)


async def resolve_page_input(
    page_text: str | None,
    page_url: str | None,
    settings: Settings,
    skip_policy_check: bool = False,
) -> tuple[ResolvedPage | None, str | None]:
    cleaned_text = (page_text or "").strip()
    cleaned_url = (page_url or "").strip() or None

    if cleaned_text:
        if len(cleaned_text) < settings.min_text_chars:
            return None, f"ページ本文は{settings.min_text_chars}文字以上入力してください。"
        timestamp_fields = build_analysis_timestamp_fields(settings)
        note = "入力された本文をそのまま解析しました。URLがある場合は参照情報としてのみ使っています。"
        return (
            ResolvedPage(
                title=pseudo_title_from_text(cleaned_text),
                site_name=urlparse(cleaned_url).netloc.replace("www.", "") if cleaned_url else "manual",
                source_url=cleaned_url,
                input_source="manual_text",
                extraction_note=note,
                analysis_date=timestamp_fields["analysis_date"],
                analysis_datetime=timestamp_fields["analysis_datetime"],
                analysis_timezone=timestamp_fields["analysis_timezone"],
                policy_check_status=None,
                policy_check_note=None,
                policy_check_url=None,
                policy_checked_urls=[],
                text_preview=build_preview(cleaned_text),
                extracted_chars=len(cleaned_text),
                has_author=False,
                has_published_at=False,
                author_name=None,
                published_at=None,
                reference_link_count=manual_reference_link_count(cleaned_text),
                paragraph_count=estimate_manual_paragraph_count(cleaned_text),
                heading_count=1,
                extraction_score=58,
                analysis_text=cleaned_text,
            ),
            None,
        )

    if cleaned_url:
        try:
            if skip_policy_check:
                html, final_url = await fetch_page_html(cleaned_url, settings)
                return parse_html_to_page(
                    html,
                    final_url,
                    settings,
                    requested_url=cleaned_url,
                    policy_status="開発用スキップ",
                    policy_note="開発用チェックボックスにより、hard block / robots.txt / 規約候補ページ確認をスキップしました。",
                    policy_check_url=None,
                    policy_checked_urls=[],
                ), None
            fetch_allowed, message, policy_status, policy_note, policy_check_url, policy_checked_urls = await is_url_fetch_allowed(cleaned_url, settings)
            if not fetch_allowed:
                return None, message
            html, final_url = await fetch_page_html(cleaned_url, settings)
            return parse_html_to_page(
                html,
                final_url,
                settings,
                requested_url=cleaned_url,
                policy_status=policy_status,
                policy_note=policy_note,
                policy_check_url=policy_check_url,
                policy_checked_urls=policy_checked_urls,
            ), None
        except httpx.HTTPStatusError as exc:
            return None, f"ページの取得に失敗しました: HTTP {exc.response.status_code}"
        except httpx.HTTPError:
            return None, "ページの取得に失敗しました。URLやネットワーク接続を確認してください。"
        except ValueError as exc:
            return None, str(exc)

    return None, "ページURLまたはページ本文を入力してください。"
