# from elasticsearch import Elasticsearch
from langchain_core.tools import tool
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, MessagesState, END, START
from langgraph.prebuilt import ToolNode
from typing import Dict, List
import os
from dotenv import load_dotenv
from openai import AzureOpenAI
import streamlit as st
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from sample_data import NODE_METRIC, POD_METRIC, APM_SAMPLE, EVENT_LOG, NODE_POD_MAP


load_dotenv()
os.environ["LANGCHAIN_TRACING_V2"] = "false"

# AI Search service
search_api_key = os.getenv("AZURE_SEARCH_API_KEY")
search_endpoint = "https://kkoldduck-search-000001.search.windows.net"
index_name = "rag-1750308489612"

search_client = SearchClient(
    endpoint=search_endpoint,
    index_name=index_name,
    credential=AzureKeyCredential(search_api_key)
)

deployment = "dev-gpt-4o-mini"
openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
llm = AzureChatOpenAI(
    azure_deployment=deployment,
    api_version="2024-12-01-preview",
    azure_endpoint="https://kkoldduck-openai-002.openai.azure.com",
    temperature=0.,
    api_key=openai_api_key
)

# ====================================
# 파라미터 추출 체인 (LLM 기반)
# ====================================
extract_prompt = ChatPromptTemplate.from_messages([
    ("system", "너는 쿠버네티스 장애 분석기야. 질문에서 다음을 JSON으로 추출해줘:\n"
               "- object_type: node | pod | service\n"
               "- object_name: 이름\n"
               "- metric: cpu | memory | disk | latency 등\n"
               "- timerange: 30m, 1h, 24h 같은 상대 시간"),
    ("human", "{question}")
])
extract_chain = extract_prompt | llm | JsonOutputParser()

# ====================================
# 쿼리 생성 함수
# ====================================
def build_metric_query(params: dict) -> dict:
    timerange = params.get("timerange", "1h")
    return {
        "index": "k8s-metric-*",
        "size": 100,
        "query": {
            "bool": {
                "must": [
                    {"term": {"node.name.keyword": params["object_name"]}},
                    {"range": {"@timestamp": {"gte": f"now-{timerange}"}}}
                ]
            }
        },
        "sort": [{"@timestamp": {"order": "desc"}}]
    }

def build_apm_query(params: dict) -> dict:
    timerange = params.get("timerange", "1h")
    return {
        "index": "apm-*",
        "size": 0,
        "query": {
            "bool": {
                "must": [
                    {"term": {"service.name.keyword": params["object_name"]}},
                    {"range": {"@timestamp": {"gte": f"now-{timerange}"}}}
                ]
            }
        },
        "aggs": {
            "avg_latency": {"avg": {"field": "transaction.duration.us"}},
            "error_rate": {"filter": {"term": {"event.outcome": "failure"}}}
        }
    }

summarize_prompt = ChatPromptTemplate.from_template(
    "다음 질문을 RAG 검색에 적합하도록 한 문장으로 핵심 요약해줘. 너무 구체적인 숫자는 생략하고 '과부하', '지연', '실패' 같은 장애 키워드 중심으로 작성해줘:\n\n질문: {query}\n\n요약:"
)
summarize_chain = summarize_prompt | llm | StrOutputParser()

# Tool 정의 : rag 검색 / 메트릭 조회
@tool
def retrieve_rag(query: str, top_k: int = 3) -> list[str]:
    """
    사용자의 자연어 질문을 기반으로 Azure Cognitive Search의 벡터 검색을 수행하여
    유사한 Kubernetes 장애 사례를 반환합니다. 검색 결과가 없을 경우 일반적인 사례를 안내합니다

    Args:
        query (str): 검색할 요약 및 히스토리 문자열
        k (int): 반환할 문서 개수 (default=3)
    Returns:
        list[str]: 유사 사례 문서 리스트
    """
    print(f"[DEBUG] retrieve_rag called with query = {query}, top_k = {top_k}")
    vector_query = VectorizableTextQuery(text=query, k_nearest_neighbors=top_k,
                                     fields="text_vector")
    results = search_client.search(search_text=query, vector_queries=[vector_query],
                                filter=None, top=top_k)
    return [
        (doc["@search.score"], doc["chunk"])
        for doc in results
    ]


@tool
def list_services_on_node(question: str) -> dict:
    """
    특정 노드에서 실행 중인 서비스 목록을 조회합니다.
    """
    params = extract_chain.invoke({"question": question})
    print(f"params: {params}")

    node_name = params.get("object_name", "").lower()  # 소문자로 표준화
    print(f"[DEBUG] list_services_on_node tool called with node_name = {node_name}")

    # ────────────────────────────────
    # 노드별 서비스 샘플 데이터
    # ────────────────────────────────
    _FAKE_NODE_SERVICE_MAP = {
        "node-a": ["checkout-service", "payment-api"],
        "node-b": ["order-service", "auth-api", "inventory-service"],
        "node-c": ["analytics-batch", "report-generator"],
    }

    services = _FAKE_NODE_SERVICE_MAP.get(node_name)
    if services is None:
        return {
            "data": [],
            "status_code": 1,
            "message": f"노드 '{node_name}'에 대한 정보가 없습니다."
        }

    return {
        "data": services,
        "status_code": 0
    }

@tool
def metric_search(question: str) -> Dict:
    """특정 노드 혹은 파드에 대한 메트릭 정보를 조회합니다."""
    params = extract_chain.invoke({"question": question})
    print(f"[DEBUG] metric_search params: {params}")

    obj_type = (params.get("object_type") or "").strip().lower()
    name = (params.get("object_name") or "").strip().lower()
    metrics = params.get("metric")

    # metric은 list or str or None 처리
    if isinstance(metrics, str):
        metrics = [metrics]
    elif metrics is None:
        metrics = []

    source = POD_METRIC if obj_type == "pod" else NODE_METRIC
    available = source.get(name)

    if not available:
        return {"data": {}, "status_code": 1, "message": f"{name}에 대한 메트릭 데이터가 없습니다."}

    result = {}
    if metrics:
        for m in metrics:
            val = available.get(f"{m}_usage") or available.get(m)
            if val: result[m] = val
    else:
        result = available  # metric 미지정 시 전체 반환

    return {"data": result, "status_code": 0} if result else {
        "data": {}, "status_code": 1, "message": f"{name}의 요청한 메트릭을 찾을 수 없습니다."
    }

@tool
def apm_search(question: str) -> dict:
    """특정 서비스에 대한 성능 지표를 조회합니다."""
    params = extract_chain.invoke({"question": question})
    print(f"[DEBUG] apm_search called with params: {params}")
    service = params.get("object_name", "").lower()
    return {"data": APM_SAMPLE.get(service, {}), "status_code": 0}

@tool
def event_search(question: str) -> dict:
    """특정 파드나 노드, PVC에 대한 이벤트 로그를 조회합니다."""
    params = extract_chain.invoke({"question": question})
    print(f"[DEBUG] event_search called with params: {params}")
    target = params.get("object_name")          # pod 이름 또는 pvc 이름
    events = EVENT_LOG.get(target, [])
    return {"data": events, "status_code": 0}

@tool
def list_pods_on_node(question: str) -> list:
    """
    특정 노드에서 실행 중인 파드 목록을 조회합니다.
    """
    params = extract_chain.invoke({"question": question})
    print(f"[DEBUG] list_pods_on_node called with params: {params}")
    node_name = params.get("object_name")    
    return NODE_POD_MAP.get(node_name, [])

class AgentState(MessagesState):
    pass

tools = [retrieve_rag, apm_search, metric_search, list_services_on_node, event_search, list_pods_on_node]
agent_engine = llm.bind_tools(tools=tools)
tool_node = ToolNode(tools)


# 모델 호출 노드
def call_model(state: AgentState):
    sys_prompt = SystemMessage(
        "당신은 쿠버네티스 SRE 전문가입니다. 다음과 같은 도구들을 사용할 수 있습니다:\n"
        "- metric_search: 노드나 파드의 상태를 분석할 때 사용합니다.\n"
        "- apm_search: 서비스의 성능 지표(지연 시간, 에러율 등)를 분석할 때 사용합니다.\n"
        "- list_services_on_node: 특정 노드에서 실행 중인 서비스 목록이 궁금할 때 사용합니다.\n"
        "- retrieve_rag: 과거의 유사 사례가 궁금할 때 사용합니다.\n\n"
        "도구를 사용하기 위해 필요한 정보가 부족하면 사용자에게 질문해서 먼저 확보하세요.\n"
        "질문에 따라 필요한 도구를 하나 이상 적절하게 호출하고, 도구 결과를 바탕으로 종합적인 분석을 제공합니다."
        "이미 호출된 도구를 반복 호출하기보다는 다음 분석 단계로 넘어가세요."
        "⚠️ 같은 도구를 반복적으로 호출하지 마세요. 이미 사용한 도구는 재사용하지 말고, 결과를 종합하여 최종 답변을 생성하세요."
    )
    response = agent_engine.invoke([sys_prompt] + state["messages"])
    return {"messages": [response]}

# 툴 호출 후 다시 모델로 돌아올지 결정
def should_continue(state: AgentState):
    last_msg = state["messages"][-1]

    # 모델이 툴 호출을 명확히 요청했을 때만 계속
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"

    # 도구 호출 끝났고, 응답 메시지가 assistant라면 종료
    return END

# --------- Define the graph
workflow = StateGraph(AgentState)

workflow.add_node("agent", call_model)
workflow.add_node("tools", tool_node)

workflow.set_entry_point("agent")
workflow.add_conditional_edges(
    "agent",
    should_continue,
    ["tools", END]
)
workflow.add_edge("tools", "agent")
graph = workflow.compile()

# ====================================
# Streamlit UI (ChatGPT 스타일)
# ====================================
content = "You are a kubernetes SRE assistant that helps users analyze and resolve issues related to Kubernetes clusters."
if "ui_messages" not in st.session_state:
    st.session_state.ui_messages = [
        {"role": "system",
         "content": content
        },
    ]
if "graph_messages" not in st.session_state:
    st.session_state.graph_messages = []     # LangChain Message 전용

# -----------------------------------------------
# UI: 타이틀 - 히스토리 출력
st.title("🛠 장애 원인 분석 시스템")
st.write("장애 상황을 입력하면 메트릭 조회 → 요약 → 유사사례 검색 → 조치방안을 추천합니다.")

for m in st.session_state.ui_messages:
    st.chat_message(m["role"]).write(m["content"])

# -----------------------------------------------
# 사용자 입력 처리
if user_input := st.chat_input("장애 상황을 입력하세요:"):
    # 1) UI 히스토리에 반영
    st.session_state.ui_messages.append({"role": "user", "content": user_input})
    st.chat_message("user").write(user_input)

    # 2) 그래프용 히스토리에 반영
    st.session_state.graph_messages.append(HumanMessage(content=user_input))

    # 3) LangGraph 실행
    with st.spinner("분석 중..."):
        state = graph.invoke({"messages": st.session_state.graph_messages})
        ai_msg = state["messages"][-1]          # LangChain AIMessage
        answer = ai_msg.content

    # 4) 두 히스토리에 AI 응답 push
    st.session_state.graph_messages.append(ai_msg)
    st.session_state.ui_messages.append({"role": "assistant", "content": answer})

    # 5) UI 출력
    st.chat_message("assistant").write(answer)

