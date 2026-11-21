"""对局分析 HTML 卡片模板渲染。"""

from dataclasses import dataclass

from ..render import CARD_WIDTH, CardTemplateContext, render_card, render_template


@dataclass(frozen=True)
class MatchAnalysisPlayerRow:
    nickname: str
    role_uri: str
    kills: int
    deaths: int
    assists: int
    damage: int
    accuracy: str
    headshot_rate: str
    personal_score: int
    strategy_score: int
    teamwork_score: int
    total_score: int
    mvp: bool
    svp: bool


@dataclass(frozen=True)
class MatchAnalysisTeamSummary:
    label: str
    theme: str
    faction_label: str
    faction_uri: str
    wins: int
    is_winner: bool
    result_label: str
    players: tuple[MatchAnalysisPlayerRow, ...]


@dataclass(frozen=True)
class MatchAnalysisStripItem:
    round_index: int
    divider_before: bool
    winner_slot: str
    reason: str
    winner_color: str


@dataclass(frozen=True)
class MatchAnalysisRoundPlayerRow:
    nickname: str
    role_uri: str
    kills: int
    deaths: int
    assists: int
    damage: int
    accuracy: str
    headshot_rate: str
    is_dead: bool


@dataclass(frozen=True)
class MatchAnalysisRoundTeamCol:
    team_label: str
    side_label: str
    theme: str
    is_winner: bool
    players: tuple[MatchAnalysisRoundPlayerRow, ...]


@dataclass(frozen=True)
class MatchAnalysisRoundItem:
    round_index: int
    phase_label: str
    score_text: str
    duration_text: str
    team_a: MatchAnalysisRoundTeamCol
    team_b: MatchAnalysisRoundTeamCol


@dataclass(frozen=True)
class MatchAnalysisTemplateContext(CardTemplateContext):
    room_id: str = ""
    mode_label: str = "对局"
    duration_text: str = "-"
    team_a: MatchAnalysisTeamSummary = MatchAnalysisTeamSummary(
        label="A队",
        theme="blue",
        faction_label="欧泊",
        faction_uri="",
        wins=0,
        is_winner=False,
        result_label="负",
        players=(),
    )
    team_b: MatchAnalysisTeamSummary = MatchAnalysisTeamSummary(
        label="B队",
        theme="red",
        faction_label="剪刀手",
        faction_uri="",
        wins=0,
        is_winner=False,
        result_label="负",
        players=(),
    )
    strip_items: tuple[MatchAnalysisStripItem, ...] = ()
    rounds: tuple[MatchAnalysisRoundItem, ...] = ()


def render_match_analysis_html(context: MatchAnalysisTemplateContext) -> str:
    """生成对局分析完整 HTML 文档。"""
    return render_template("match_analysis_card.html", context)


async def render_match_analysis_card(context: MatchAnalysisTemplateContext) -> bytes:
    """把对局分析渲染成 PNG 卡片。"""
    return await render_card(
        "match_analysis_card.html",
        context,
        width=CARD_WIDTH,
        default_font_size=14,
    )
