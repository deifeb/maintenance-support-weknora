from maintenance_ai.enums import UserIntent

_INTENT_TERMS = {
    UserIntent.DEMAND_CALCULATE: ("计算", "推算", "需求"),
    UserIntent.DEMAND_LIST_REVIEW: ("审查", "审核"),
    UserIntent.REPORT_GENERATE: ("报告", "导出"),
    UserIntent.INVENTORY_GAP_ANALYZE: ("缺口", "库存"),
    UserIntent.TASK_CANCEL: ("取消",),
    UserIntent.TASK_STATUS_QUERY: ("进度", "状态"),
}


def classify_intent(text: str) -> UserIntent:
    for intent, terms in _INTENT_TERMS.items():
        if any(term in text for term in terms):
            return intent
    return UserIntent.GENERAL_QA
