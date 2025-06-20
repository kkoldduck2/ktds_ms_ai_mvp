# 0. **서비스 접속 주소**
https://sjkim0831-gcfad7f9a5ahh6fh.swedencentral-01.azurewebsites.net/

# 1. **개요 및 목적**

### 1) 현재 모니터링 시스템 개요

- 현재 **ICIS Tr 모니터링 시스템**에서는
    
    쿠버네티스 환경에서 발생하는 **메트릭, 이벤트, 로그, APM 데이터**가
    
    모두 **Elasticsearch에 중앙 집중 방식으로 저장**되고 있습니다.
    
- 운영자는 Kibana를 통해 직접 로그를 조회하거나,
    
    **Kibana 사용에 익숙하지 않은 사용자**를 위해 별도로 개발된 UI인 **NEONE**을 통해 모니터링을 진행합니다.

![Image](https://github.com/user-attachments/assets/6da01dc0-382c-482f-919e-6fc12f4bfbfd)


### 2) 현재 시스템의 보완 지점

1. **Kibana에서 원하는 정보를 찾기 어렵다**
    - NEONE에서 주요 지표는 확인할 수 있지만,
        
        보다 세부적인 원인을 파악하려면 Kibana에서 직접 데이터를 조회해야 합니다.
        
    - 그러나 Kibana는 **초심자에게 진입 장벽이 높고**,
        
        어떤 필드를 보고 어떻게 필터링해야 할지 알기 어렵습니다.
        
2. **과거 장애 사례를 참고하기 어렵다**
    - 유사한 문제가 과거에 발생했는지,
        
        있었다면 **어떻게 해결했는지를 추적하기가 어렵습니다.**
        

### 3) 서비스 도입의 필요성

- **자연어 질문을 바탕으로 Elasticsearch 쿼리를 자동 생성**하고,
    
    관련 메트릭·로그 데이터를 조회해서 바로 보여주는 **AI 기반의 분석 도우미**가 있다면
    
    운영자 입장에서 훨씬 직관적인 문제 해결이 가능할 것입니다.
    
- 더 나아가, **RAG 기반 검색을 통해 과거 유사한 장애 사례를 찾아**,
    
    **당시의 해결 방안까지 추천해주는 기능**이 있다면,
    
    **문제 진단 속도를 획기적으로 줄일 수 있다**고 판단했습니다.
    

# 2. 시스템 아키텍처 및 코드 구성

### 1) 주요 기능과 아키텍처 개요

- **사용자 질문**을 입력하면,
- **LangChain 기반 LLM**이 질문을 이해하고 필요한 정보를 추출한 뒤,
- *도구(tool)**를 호출해 **메트릭 / 이벤트 / APM / 유사사례(RAG)** 를 조회함
- 결과를 **Streamlit UI**에 자연어로 응답

```
[ 사용자 입력 ]
      ↓
[ LLM (GPT-4o-mini) + 툴 선택 ]
      ↓
[ Elasticsearch 기반 메트릭/로그/APM + RAG ]
      ↓
[ 종합 응답 생성 → 사용자 출력 ]
```

### 2) 핵심 구성 요소

| 구성 요소 | 설명 |
| --- | --- |
| **LLM (Azure GPT-4o-mini)** | 사용자 질문을 이해하고 툴 호출 흐름을 제어 |
| **LangChain Tool** | 메트릭, 로그, APM, RAG 등 기능별 도구 정의 |
| **StateGraph (LangGraph)** | 도구 호출 → 모델 응답 → 종합 판단 흐름을 제어 |
| **Azure AI Search** | 과거 장애 리포트 검색 (RAG) 수행 |
| **Streamlit** | 사용자가 인터랙션할 수 있는 웹 인터페이스 제공 |

### 3) 전체 동작 흐름

**1. 사용자 질문 입력**

- Streamlit `st.chat_input`을 통해 자연어 질문 수집

**2. 모델이 적절한 도구(Tool)를 선택**

- LLM은 SystemMessage의 지시를 기반으로 `metric_search`, `apm_search`, `event_search`, `retrieve_rag` 등 중에서 필요한 도구를 자동 선택
- 질문 의도에 따라 도구를 **하나 또는 여러 개 순차 호출**

**3. 선택된 도구 실행 시, 내부에서 파라미터 추출**

- 각 Tool 내부에서 `extract_chain`을 통해 필요한 정보를 파싱
- 예: `"node-a의 디스크 사용량이 높은 것 같아"` →
    
    `{"object_type": "node", "object_name": "node-a", "metric": "disk"}`
    

**4. 데이터 조회 및 분석 결과 반환**

- 실제 쿼리는 샘플 데이터 혹은 Elasticsearch 연동 후 이뤄짐
- Tool의 응답은 다시 LLM에 전달됨

**5. 필요시 반복 분석 수행**

- LangGraph의 `StateGraph` 조건 분기를 통해 툴을 추가 호출하거나 종료 결정
- ex) `metric_search` → 결과 보고 `retrieve_rag` 호출

**6. 최종 자연어 응답 생성**

- LLM이 모든 툴 응답을 종합해 사용자에게 최종 답변을 반환


### 4) LangGraph 흐름 구조

```python
graph = StateGraph(AgentState)

graph.add_node("agent", call_model)     # LLM 판단
graph.add_node("tools", tool_node)      # 툴 실행

graph.set_entry_point("agent")
graph.add_conditional_edges("agent", should_continue, ["tools", END])
graph.add_edge("tools", "agent")
graph.compile()
```

- LangGraph를 사용해 **“모델 호출 → 툴 실행 → 판단 반복”** 구조를 설계

# 3. 향후 개발 계획

- **Elasticsearch 연동 쿼리 생성 기능 구현**
    
    현재는 사전 정의된 mock 데이터를 기반으로 동작하고 있으며, 향후에는 사용자 질의를 바탕으로 **실제 Elasticsearch 쿼리를 동적으로 생성**하고 실행할 수 있도록 기능을 확장할 예정입니다.
    
- **장애 보고서 RAG 체계 고도화**
    
    유사 장애 검색을 위한 RAG 시스템의 정확도를 높이기 위해, **정형화된 장애 보고서 작성 포맷**을 마련하고, 다양한 실 사례를 수집하여 벡터 데이터베이스를 고도화할 계획입니다.
