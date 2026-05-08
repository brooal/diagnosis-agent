
from app.tools.base import ToolResult, ToolSpec

def query_pv_at_time(pv_name : str, timestamp : str) -> ToolResult:
    value = 120.5

    return ToolResult(
        ok=True,
        output={
            "pv_name" : pv_name,
            "timestamp" : timestamp,
            "value" : value,
        },
        summary= f"{pv_name} 在 {timestamp} 的值为 {value}",

    )

query_pv_at_time_spec = ToolSpec(
    name="query_pv_at_time",
    description = "查询某个PV在指定时刻附近的值",
    parameters={
        "type" : "object",
        "properties" : {
            "pv_name" : {
                "type" : "string",
                "descriptions" : "PV名称",
            },
            "timestamp" : {
                "type" : "string",
                "description" : "ISO8601 时间字符串",
            }
        },
        "required" : ["pv_name" ,"timestamp"],
    },
    handler=query_pv_at_time,
)

#一段时间范围内的故障诊断
def query_pv_range(pv_name: str, start: str, end: str) -> ToolResult:
    # mock：真实场景中这里查询时序数据库
    result = {
        "pv_name": pv_name,
        "start": start,
        "end": end,
        "min": 0.1,
        "max": 120.5,
        "avg": 80.3,
        "drop_detected": True,
        "drop_time": "2026-05-06T10:02:31+09:00",
    }

    return ToolResult(
        ok=True,
        output=result,
        summary=(
            f"{pv_name} 在 {start} 到 {end} 范围内出现跌落，"
            f"跌落时间约为 {result['drop_time']}"
        ),
    )


query_pv_range_spec = ToolSpec(
    name="query_pv_range",
    description="查询某个 PV 在时间范围内的统计信息和简单异常特征。",
    parameters={
        "type": "object",
        "properties": {
            "pv_name": {"type": "string"},
            "start": {"type": "string"},
            "end": {"type": "string"},
        },
        "required": ["pv_name", "start", "end"],
    },
    handler=query_pv_range,
)
