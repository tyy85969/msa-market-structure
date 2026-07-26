from msa.validation import MetricEventKind, default_metric_formula_registry
from msa.validation.metrics.identity import digest

from .fixtures import base_report, direction_report, touch_report


FORMULA_IDS = (
    "structural-metric-formula-v1-2c7decb9fe0b467b7a6657d5f6de93616c6812856241408ec8b27aa4a514a4a7",
    "structural-metric-formula-v1-79b56946e27b6148c29bf2feb0e353ea56ed63ab5b8d76bd78c663b5a258b0be",
    "structural-metric-formula-v1-adb7111f762dae6333e9b1b4909adbe1dacc747f46f7f4a538d40e8169bca252",
    "structural-metric-formula-v1-aa132f95e6c99a455c5dbde0a9f3bc3dcf42cb308aead9a207009cf74758e336",
    "structural-metric-formula-v1-835f5b5e402afcbe4600a9b0d65bb67a3bd0d2d3e7bd8e2bb3e8ba8012bb168e",
    "structural-metric-formula-v1-10cf69b7fd7c29da30d6d0bd49e0271185a74c19a1edca033130668b16ea235e",
    "structural-metric-formula-v1-3e6b49755b7e97f72f8e29a5cc4d68e3a077a4dffa638abc58fdf23f0e89f72a",
    "structural-metric-formula-v1-0da0a0564d79e4893a4f77d6f4d5ada061cb6268db63e14c3b90e5d1cfc7a156",
    "structural-metric-formula-v1-430e5cc1d576b149622c6136be1a080ecbe426528c8c6a1a1cad704ab96dcabe",
    "structural-metric-formula-v1-44f487cd0cc5d2b3feeb7f21cb41ee1a7ae46c3ec775d42aed15c3f47084be8a",
)


def first_event_id(report, kind: MetricEventKind) -> str:
    return next(
        item.metric_event_id for item in report.events if item.kind is kind
    )


def test_formula_and_representative_event_ids_are_frozen() -> None:
    base = base_report()
    direction = direction_report()
    touch = touch_report()
    assert tuple(
        item.metric_formula_id for item in default_metric_formula_registry()
    ) == FORMULA_IDS
    assert first_event_id(base, MetricEventKind.STRUCTURE_CONFIRMATION) == (
        "structural-metric-event-v1-8a5c0e23874a7f1bafb2a2f7c0090295f6859415dc6a53d35e0ba13a994e1ab4"
    )
    assert first_event_id(direction, MetricEventKind.TURN_CANDIDATE) == (
        "structural-metric-event-v1-b1cb849f3b82bb75d08c910a6ae7f9284fa57b12c942ee001841e3ebd090cbb9"
    )
    assert first_event_id(direction, MetricEventKind.BREAK_CONFIRMATION) == (
        "structural-metric-event-v1-ae887eb58400265a6e8219547b882a61e71406e8eb21d9496d2b7f1a3eed7889"
    )
    assert first_event_id(base, MetricEventKind.BOX_EPISODE_CREATED) == (
        "structural-metric-event-v1-bf7a0a5a918095124693bb3a430f24d937c089b0c0002078c1bcb3509373799d"
    )
    touches = tuple(
        item
        for item in touch.events
        if item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
    )
    assert tuple(item.metric_event_id for item in touches) == (
        "structural-metric-event-v1-89fe4b65a2ee673d53e19355567a45670480fbba0d644c74a032d59a8852ef15",
        "structural-metric-event-v1-c92264eda5491446454888424acdb185cfd96835fd7bbee6278b1de01237956d",
    )


def test_complete_report_digests_and_aggregate_ids_are_frozen() -> None:
    base = base_report()
    touch = touch_report()
    assert digest(base.to_dict()) == (
        "18620a9201d4653a19cb6b95b0a02702c61e0f8e89bc2af92467b7c50169a245"
    )
    assert digest(touch.to_dict()) == (
        "63c90ead3b17519c46f5b6be62347f8a8a1c367ca8b4854072e7b6f6f4837382"
    )
    assert base.metric_report_id == (
        "metric-evaluation-report-v1-71fde14a57aece646dd345c88234dde0e46ba60454030342e407de01b8d92519"
    )
    assert len(tuple(item.metric_aggregate_id for item in base.aggregates)) == 10
    assert tuple(item.metric_aggregate_id for item in base.aggregates) == (
        "structural-metric-aggregate-v1-707fa0ff9f992592e3958bd65e292f13464f4108920d1987dabb4de6be9c2b8c",
        "structural-metric-aggregate-v1-31659959ac7cdfd4e434daea4716719cbf0d81b194d8617f41c1c150e48c962c",
        "structural-metric-aggregate-v1-664401aa22f2c069b6c8fb1b235ec12d219d154fc445038da7a3626565c596ac",
        "structural-metric-aggregate-v1-00fceecbf0545bae07c2e581df3988779223981dbe354ce16697643b3ede0b6d",
        "structural-metric-aggregate-v1-a86e9df2265a4719c53575c2ae47e88b86f137026265e4e29907ee40a016d0a9",
        "structural-metric-aggregate-v1-51de7c0fadada888a84dc4705cc920fa07833be7e3613688502c73cd7326d32b",
        "structural-metric-aggregate-v1-de6f55e05d0bf47bdc2b04ac17cd4a5c03a6441b15534b092221db0bcad65e38",
        "structural-metric-aggregate-v1-4eca54077c6265a1907dbe68f5822fd64ab834274585b0396a8adf99e3ae3cb8",
        "structural-metric-aggregate-v1-4c209b602d22a0bc7b7b4e9cfa0ab0eba95a790e7b3ab63910ed9ee596e8f913",
        "structural-metric-aggregate-v1-5cbdfc32f7d3a3497efd8e5470b641f802e5d78a74af1d594215fa727e4ecf36",
    )
