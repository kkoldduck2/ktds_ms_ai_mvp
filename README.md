# 0. **서비스 접속 주소**
https://sjkim0831-gcfad7f9a5ahh6fh.swedencentral-01.azurewebsites.net/

# 1. **개요 및 목적**

### 1) 현재 모니터링 시스템 개요
![image](https://github.com/user-attachments/assets/71fe18e5-ca6e-469f-8341-5699aff9daf7)

- 쿠버네티스 환경에서 발생하는 **메트릭, 이벤트, 로그, APM 데이터**가 **Elasticsearch에 중앙 집중 저장**
- 운영자는 **Kibana** 또는 자체 개발 UI **NEONE**을 통해 모니터링 수행

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
        

### 3) 서비스 도입의 필요성

- **자연어 질문** → **Elasticsearch 쿼리 자동 생성** → **즉시 결과 제공**
- **RAG 기반 과거 사례 검색**으로 유사 장애 해결 방안 제시
- **AI 기반 분석 도우미**로 **문제 진단 속도 획기적 개선**
    

# 2. 시스템 아키텍처 및 코드 구성

### 1) 주요 기능과 아키텍처 개요

- 사용자가 질문을 입력하면,
- **LLM이 질문의 의도를 파악하여 적절한 도구(tool)를 선택**하고,
- **선택된 도구 내부에서 파라미터를 추출**해 메트릭 / 이벤트 / APM / 유사사례(RAG)를 조회합니다.
- 이렇게 조회된 결과는 다시 LLM으로 전달되고,
- **LLM은 이를 종합하여 자연어 형태로 Streamlit UI에 응답합니다.**

![image](https://github.com/user-attachments/assets/58e264cc-dbc3-4e4b-87e3-d45100c13b71)


### 2) 핵심 구성 요소

| 구성 요소 | 설명 |
| --- | --- |
| **LLM (Azure GPT-4o-mini)** | 사용자 질문을 이해하고 툴 호출 흐름을 제어 |
| **LangChain Tool** | 메트릭, 로그, APM, RAG 등 기능별 도구 정의 |
| **StateGraph (LangGraph)** | 도구 호출 → 모델 응답 → 종합 판단 흐름을 제어 |
| **Azure AI Search** | 과거 장애 리포트 검색 (RAG) 수행 |
| **Streamlit** | 사용자가 인터랙션할 수 있는 웹 인터페이스 제공 |

### 3) 전체 동작 흐름
![image](https://github.com/user-attachments/assets/987986b6-c3cc-4d0d-84e7-95561d8b8fd4)


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


# 3. 향후 개발 계획

- **Elasticsearch 연동 쿼리 생성 기능 구현**
    
    현재는 사전 정의된 mock 데이터를 기반으로 동작하고 있으며, 향후에는 사용자 질의를 바탕으로 **실제 Elasticsearch 쿼리를 동적으로 생성**하고 실행할 수 있도록 기능을 확장할 예정입니다.
    
- **장애 보고서 RAG 체계 고도화**
    
    유사 장애 검색을 위한 RAG 시스템의 정확도를 높이기 위해, **정형화된 장애 보고서 작성 포맷**을 마련하고, 다양한 실 사례를 수집하여 벡터 데이터베이스를 고도화할 계획입니다.
