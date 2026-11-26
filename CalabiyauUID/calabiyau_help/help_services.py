"""卡拉彼丘帮助图渲染、默认贴图准备与 Steam 背景后台更新。"""

import os
import json
import shutil
import asyncio
from pathlib import Path

import aiofiles
from PIL import Image, ImageDraw, ImageFilter, UnidentifiedImageError

from gsuid_core.sv import get_plugin_available_prefix
from gsuid_core.pool import to_thread
from gsuid_core.logger import logger
from gsuid_core.help.model import PluginSV, PluginHelp
from gsuid_core.utils.fonts.fonts import core_font
from gsuid_core.help.draw_new_plugin_help import get_new_help

from ..version import CalabiyauUID_version
from ..utils.api.steam import fetch_steam_help_assets
from ..utils.downloader import download_to_dir
from ..utils.utils.paths import DATA_DIR
from ..utils.utils.background import track_background_task

ICON: Path = Path(__file__).parent.parent.parent / "ICON.png"
HELP_DATA: Path = Path(__file__).parent / "help.json"
ICON_PATH: Path = Path(__file__).parent / "icon_path"
PLUGIN_TEXT_PATH: Path = Path(__file__).parent / "texture2d"

DATA_HELP_TEXT_DIR: Path = DATA_DIR / "help" / "texture2d"
DATA_BANNER_PATH: Path = DATA_HELP_TEXT_DIR / "banner_bg.jpg"
DATA_BG_PATH: Path = DATA_HELP_TEXT_DIR / "bg.jpg"
DATA_BG_BLUR_PATH: Path = DATA_HELP_TEXT_DIR / "bg_blur.jpg"
DATA_HASH_PATH: Path = DATA_HELP_TEXT_DIR / "hash"

_BANNER_WIDTH = 1545
_BG_MAX_WIDTH = 600
_JPEG_QUALITY = 85
_BLUR_RADIUS = 12
_BANNER_SUB_TEXT = "喵拉喵丘喵了喵！~"
_FOOTER_TEXT = "Create by GsCore & Power by CalabiyauUID & Author by sssysy"
_LOG_TAG = "[卡拉彼丘·帮助]"


def _is_nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _atomic_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def _save_jpeg_atomic(image: Image.Image, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f".{dst.name}.tmp")
    rgb = image.convert("RGB")
    rgb.save(tmp, format="JPEG", quality=_JPEG_QUALITY, optimize=True, progressive=True)
    with Image.open(tmp) as check:
        check.verify()
    os.replace(tmp, dst)


def _render_blurred_bg(bg_path: Path, blur_dst: Path) -> None:
    with Image.open(bg_path) as raw:
        blurred = raw.convert("RGB").filter(ImageFilter.GaussianBlur(radius=_BLUR_RADIUS))
    _save_jpeg_atomic(blurred, blur_dst)


def ensure_help_textures() -> None:
    """启动时同步补全 data 下的帮助底图，并在注册前完成模糊处理。"""
    DATA_HELP_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    if not _is_nonempty_file(DATA_BANNER_PATH):
        _atomic_copy(PLUGIN_TEXT_PATH / "banner_bg.jpg", DATA_BANNER_PATH)

    bg_copied = False
    if not _is_nonempty_file(DATA_BG_PATH):
        _atomic_copy(PLUGIN_TEXT_PATH / "bg.jpg", DATA_BG_PATH)
        bg_copied = True

    if bg_copied or not _is_nonempty_file(DATA_BG_BLUR_PATH):
        _render_blurred_bg(DATA_BG_PATH, DATA_BG_BLUR_PATH)


def load_plugin_icon() -> Image.Image:
    """加载插件图标副本，避免长期占用文件句柄。"""
    with Image.open(ICON) as img:
        return img.copy()


def _load_image_copy(path: Path) -> Image.Image:
    with Image.open(path) as img:
        return img.copy()


def _build_help_footer() -> Image.Image:
    footer = Image.new("RGBA", (1200, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(footer)
    draw.text(
        (600, 40),
        _FOOTER_TEXT,
        fill=(220, 225, 232, 220),
        font=core_font(28),
        anchor="mm",
    )
    return footer


def _parse_plugin_sv(item: object) -> PluginSV | None:
    if not isinstance(item, dict):
        return None
    name = item["name"] if "name" in item else None
    desc = item["desc"] if "desc" in item else None
    eg = item["eg"] if "eg" in item else None
    highlight = item["highlight"] if "highlight" in item else 0
    need_ck = item["need_ck"] if "need_ck" in item else False
    need_sk = item["need_sk"] if "need_sk" in item else False
    need_admin = item["need_admin"] if "need_admin" in item else False
    if (
        not isinstance(name, str)
        or not isinstance(desc, str)
        or not isinstance(eg, str)
        or not isinstance(highlight, int)
        or not isinstance(need_ck, bool)
        or not isinstance(need_sk, bool)
        or not isinstance(need_admin, bool)
    ):
        return None
    return PluginSV(
        name=name,
        desc=desc,
        eg=eg,
        highlight=highlight,
        need_ck=need_ck,
        need_sk=need_sk,
        need_admin=need_admin,
    )


def _parse_help_data(raw: object) -> dict[str, PluginHelp]:
    if not isinstance(raw, dict):
        raise ValueError("help.json 根节点必须为字典")
    result: dict[str, PluginHelp] = {}
    for cag_name, cag_body in raw.items():
        if not isinstance(cag_name, str) or not isinstance(cag_body, dict):
            continue
        desc = cag_body["desc"] if "desc" in cag_body else ""
        raw_items = cag_body["data"] if "data" in cag_body else []
        if not isinstance(desc, str) or not isinstance(raw_items, list):
            continue
        entries: list[PluginSV] = []
        for item in raw_items:
            parsed = _parse_plugin_sv(item)
            if parsed is not None:
                entries.append(parsed)
        result[cag_name] = PluginHelp(desc=desc, data=entries)
    return result


async def get_help_data() -> dict[str, PluginHelp]:
    """异步读取并校验 help.json。"""
    async with aiofiles.open(HELP_DATA, "rb") as file:
        raw: object = json.loads(await file.read())
    return _parse_help_data(raw)


@to_thread
def _read_local_hashes() -> tuple[str, str]:
    if not DATA_HASH_PATH.is_file():
        return "", ""
    banner_hash = ""
    bg_hash = ""
    for line in DATA_HASH_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("banner="):
            banner_hash = stripped.removeprefix("banner=").strip()
        elif stripped.startswith("bg="):
            bg_hash = stripped.removeprefix("bg=").strip()
    return banner_hash, bg_hash


@to_thread
def _write_local_hashes(banner_hash: str, bg_hash: str) -> None:
    DATA_HELP_TEXT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = DATA_HASH_PATH.with_name(".hash.tmp")
    tmp.write_text(f"banner={banner_hash}\nbg={bg_hash}\n", encoding="utf-8")
    os.replace(tmp, DATA_HASH_PATH)


@to_thread
def _process_downloaded_banner(download_path: Path) -> bool:
    try:
        with Image.open(download_path) as raw:
            rgb = raw.convert("RGB")
            if rgb.width != _BANNER_WIDTH:
                new_h = max(1, round(rgb.height * _BANNER_WIDTH / rgb.width))
                rgb = rgb.resize((_BANNER_WIDTH, new_h), Image.Resampling.LANCZOS)
            _save_jpeg_atomic(rgb, DATA_BANNER_PATH)
        return True
    except (OSError, UnidentifiedImageError) as exc:
        logger.warning(f"{_LOG_TAG} 处理下载的 banner_bg 失败：{exc}")
        return False
    finally:
        download_path.unlink(missing_ok=True)


@to_thread
def _process_downloaded_bg(download_path: Path) -> bool:
    try:
        with Image.open(download_path) as raw:
            rgb = raw.convert("RGB")
            if rgb.width > _BG_MAX_WIDTH:
                new_h = max(1, round(rgb.height * _BG_MAX_WIDTH / rgb.width))
                rgb = rgb.resize((_BG_MAX_WIDTH, new_h), Image.Resampling.LANCZOS)
            bg_tmp = DATA_BG_PATH.with_name(f".{DATA_BG_PATH.name}.tmp")
            rgb.save(bg_tmp, format="JPEG", quality=_JPEG_QUALITY, optimize=True, progressive=True)
            with Image.open(bg_tmp) as check:
                check.verify()

            blurred = rgb.filter(ImageFilter.GaussianBlur(radius=_BLUR_RADIUS))
            blur_tmp = DATA_BG_BLUR_PATH.with_name(f".{DATA_BG_BLUR_PATH.name}.tmp")
            blurred.save(blur_tmp, format="JPEG", quality=_JPEG_QUALITY, optimize=True, progressive=True)
            with Image.open(blur_tmp) as check:
                check.verify()

            os.replace(bg_tmp, DATA_BG_PATH)
            os.replace(blur_tmp, DATA_BG_BLUR_PATH)
        return True
    except (OSError, UnidentifiedImageError) as exc:
        logger.warning(f"{_LOG_TAG} 处理下载的 bg 失败：{exc}")
        return False
    finally:
        download_path.unlink(missing_ok=True)


async def sync_steam_help_backgrounds() -> None:
    """后台比对 SteamCMD hash 并无缝替换 data 下的帮助背景图。"""
    assets = await fetch_steam_help_assets()
    if assets is None:
        return

    local_banner_hash, local_bg_hash = await _read_local_hashes()
    need_banner = local_banner_hash != assets.banner_hash or not _is_nonempty_file(DATA_BANNER_PATH)
    need_bg = (
        local_bg_hash != assets.bg_hash
        or not _is_nonempty_file(DATA_BG_PATH)
        or not _is_nonempty_file(DATA_BG_BLUR_PATH)
    )
    if not need_banner and not need_bg:
        logger.info(f"{_LOG_TAG} Steam 帮助背景已是最新，跳过下载")
        return

    next_banner_hash = local_banner_hash
    next_bg_hash = local_bg_hash

    if need_banner:
        banner_dl = await download_to_dir(
            assets.banner_url,
            DATA_HELP_TEXT_DIR,
            ".banner_bg.download.tmp",
            tag=_LOG_TAG,
        )
        if banner_dl is not None and await _process_downloaded_banner(banner_dl):
            next_banner_hash = assets.banner_hash
            logger.success(f"{_LOG_TAG} 已更新 Steam banner_bg（hash={assets.banner_hash}）")

    if need_bg:
        bg_dl = await download_to_dir(
            assets.bg_url,
            DATA_HELP_TEXT_DIR,
            ".bg.download.tmp",
            tag=_LOG_TAG,
        )
        if bg_dl is not None and await _process_downloaded_bg(bg_dl):
            next_bg_hash = assets.bg_hash
            logger.success(f"{_LOG_TAG} 已更新 Steam bg 与 bg_blur（hash={assets.bg_hash}）")

    if next_banner_hash != local_banner_hash or next_bg_hash != local_bg_hash:
        await _write_local_hashes(next_banner_hash, next_bg_hash)


def start_steam_background_sync() -> None:
    """启动不阻断 Core 启动流程的后台背景更新任务。"""
    task = asyncio.create_task(sync_steam_help_backgrounds(), name="calabiyau_help_bg_sync")
    track_background_task(task, log_tag=_LOG_TAG, error_label="后台更新帮助背景异常")


@to_thread
def _load_help_textures() -> tuple[Image.Image, Image.Image, Image.Image, Image.Image, Image.Image, Image.Image]:
    if not _is_nonempty_file(DATA_BANNER_PATH) or not _is_nonempty_file(DATA_BG_BLUR_PATH):
        ensure_help_textures()
    banner_bg = _load_image_copy(DATA_BANNER_PATH)
    help_bg = _load_image_copy(DATA_BG_BLUR_PATH)
    cag_bg = _load_image_copy(PLUGIN_TEXT_PATH / "cag_bg.png")
    item_bg = _load_image_copy(PLUGIN_TEXT_PATH / "item.png")
    plugin_icon = load_plugin_icon()
    footer = _build_help_footer()
    return plugin_icon, banner_bg, help_bg, cag_bg, item_bg, footer


async def get_calabiyau_help(user_pm: int = 6) -> bytes | str:
    """生成 CalabiyauUID 帮助图。"""
    plugin_help = await get_help_data()
    plugin_icon, banner_bg, help_bg, cag_bg, item_bg, footer = await _load_help_textures()
    prefix = get_plugin_available_prefix("CalabiyauUID")
    return await get_new_help(
        plugin_name="CalabiyauUID",
        plugin_info={f"v{CalabiyauUID_version}": ""},
        plugin_icon=plugin_icon,
        plugin_help=plugin_help,
        plugin_prefix=prefix,
        help_mode="dark",
        banner_bg=banner_bg,
        banner_sub_text=_BANNER_SUB_TEXT,
        help_bg=help_bg,
        cag_bg=cag_bg,
        item_bg=item_bg,
        icon_path=ICON_PATH,
        footer=footer,
        column=4,
        need_cover=True,
        enable_cache=True,
        pm=user_pm,
    )
