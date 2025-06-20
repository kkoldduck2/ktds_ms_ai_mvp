# RAG 기반 이상징후 탐지 및 장애 대응 지원 시스템


## 1. **프로젝트 배경**

### 1) 현재 모니터링 시스템 개요
![image](https://github.com/user-attachments/assets/71fe18e5-ca6e-469f-8341-5699aff9daf7)

- 쿠버네티스 환경에서 발생하는 **메트릭, 이벤트, 로그, APM 데이터**가 **Elasticsearch에 중앙 집중 저장**
- 운영자는 **Kibana** 또는 자체 개발 UI를 통해 모니터링 수행

![Image](https://github.com/user-attachments/assets/6da01dc0-382c-482f-919e-6fc12f4bfbfd)


### 2) 현재 시스템의 보완 지점

1. **Kibana 접근성 이슈**
    - NEONE에서 주요 지표 확인 가능하지만, **세부 원인 파악**을 위해서는 Kibana 직접 사용 필요
    - Kibana는 **초심자에게 진입 장벽이 높음**
    - 어떤 필드를 보고 어떻게 필터링해야 할지 파악 어려움
        
        보다 세부적인 원인을 파악하려면 Kibana에서 직접 데이터를 조회해야 합니다.
        
2. **과거 장애 사례 추적 어려움**
    - 유사한 문제가 과거에 발생했는지 확인 어려움
    - 과거 해결 방안을 **체계적으로 추적하고 활용하기 어려운 구조**
        

### 3) 기대 효과

- **자연어 질문** → **Elasticsearch 쿼리 자동 생성** → **즉시 결과 제공**
- **RAG 기반 과거 사례 검색**으로 유사 장애 해결 방안 제시
- **AI 기반 분석 도우미**로 **문제 진단 속도 획기적 개선**
    

## 2. 시스템 아키텍처 및 코드 구성

### 1) 주요 기능과 아키텍처 개요
![image](https://github.com/user-attachments/assets/df89aac7-a940-4cab-a3e3-3b06cd84a584)

**1. 사용자 질문 입력**

- Streamlit `st.chat_input`을 통해 자연어 질문 수집

**2. 모델이 적절한 도구(Tool)를 선택**

- LLM은 SystemMessage의 지시를 기반으로 `metric_search`, `apm_search`, `event_search`, `retrieve_rag` 등 중에서 필요한 도구를 자동 선택
- 질문 의도에 따라 도구를 **하나 또는 여러 개 순차 호출**

**3. 선택된 도구 실행 시, 내부에서 파라미터 추출**

- 각 Tool 내부에서 `extract_chain`을 통해 필요한 파라미터 추출
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




### 2) 핵심 구성 요소

| 구성 요소 | 역할 및 기능 |
| --- | --- |
| **LLM (Azure GPT-4o-mini)** | 사용자 질문을 이해하고 툴 호출 흐름을 제어 |
| **LangChain Tool** | 메트릭, 로그, APM, RAG 등 기능별 도구 정의 |
| **StateGraph (LangGraph)** | 도구 호출 → 모델 응답 → 종합 판단 흐름을 제어 |
| **Azure AI Search** | 과거 장애 리포트 검색 (RAG) 수행 |
| **Streamlit** | 사용자가 인터랙션할 수 있는 웹 인터페이스 제공 |
| **Elasticsearch** | 메트릭, 로그, APM 데이터의 실시간 검색 및 분석 엔진 |


### 3) 전체 동작 흐름
![image](https://github.com/user-attachments/assets/987986b6-c3cc-4d0d-84e7-95561d8b8fd4)



## 3. 시연
https://sjkim0831-gcfad7f9a5ahh6fh.swedencentral-01.azurewebsites.net/


## 4. 향후 개발 계획
- **Elasticsearch 연동 쿼리 생성 기능 구현**
    - **현재 상태**: 사전 정의된 mock 데이터 기반 동작
    - **개발 목표**: 사용자 질의를 바탕으로 **실제 Elasticsearch 쿼리를 동적으로 생성**하고 실행
    - **구현 방향**:
        
        ```python
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
        ```
        
- **장애 보고서 RAG 체계 고도화**
    - **현재 상태**: 기본적인 RAG 구조 구현
    - **개발 목표**:
        - **정형화된 장애 보고서 작성 포맷** 마련
        - 다양한 실 사례 수집 및 **벡터 데이터베이스 고도화**
        - 검색 정확도 향상을 위한 **임베딩 모델 최적화**
          
- **UI 개선을 통한 데이터 시각화 기능 추가 -> 자체 개발 UI에 통합**
    - **시계열 데이터** → 라인 차트, 영역 차트
    - **APM 데이터** → 응답시간 분포, 에러율 트렌드
    - **메트릭 비교** → 바 차트, 히트맵
