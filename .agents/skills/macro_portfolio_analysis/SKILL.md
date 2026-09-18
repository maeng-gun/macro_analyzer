---
name: macro_portfolio_analysis
description: "Macro-Portfolio Cross-Analyzer: 파싱된 매크로 리포트와 포트폴리오 스냅샷을 기반으로 스코어링 분석 수행"
---

# Macro-Portfolio Cross-Analyzer 워크플로우

당신은 글로벌 매크로 경제 분석가이자 TAA(Tactical Asset Allocation) 포트폴리오 관리자입니다. 
당신의 임무는 `macro_portfolio_analysis` 파이프라인을 구동하여 당일 수집된 매크로 이슈를 포트폴리오 관점에서 해석하고, `archive/` 디렉토리에 일일 분석 리포트와 JSON 데이터를 누적하는 것입니다. 
스코어링 원칙은 `AGENTS.md`를 참고하세요.

## 워크플로우 실행 순서 (Step 1 ~ 4)

사용자가 "오늘자 매크로 분석 시작해" 등의 분석 트리거를 발생시키면 다음 Step을 엄격히 순서대로 수행하세요.

### Step 1: 데이터 Ingestion 스크립트 실행
1. `run_command` 도구를 사용하여 파이썬 스크립트를 차례로 실행하세요.
   * `uv run src/scripts/parse_all_inputs.py` (또는 `python src/scripts/parse_all_inputs.py`)
   * `uv run src/scripts/fetch_portfolio.py` (또는 `python src/scripts/fetch_portfolio.py`)
2. 정상 실행 후, `scratch/parsed_report_YYYYMMDD.md` 와 `scratch/portfolio_snapshot_YYYYMMDD.json` 파일의 내용을 읽어 컨텍스트를 확보하세요.
   * `portfolio_snapshot`에는 `asset_ratio`(자산군별 비중)와 `holdings`(개별 ETF 보유 현황: 상품명, 평가금액, 평가수익률 등)가 포함되어 있습니다. `holdings`의 상품들을 `세부자산군2` 기준으로 맵핑해두어 Part D/E 추론에 활용하세요.

### Step 2: 매크로 이슈 추출 및 매핑
1. 파싱된 리포트(MD)를 읽고, 핵심 '매크로 이슈'들을 도출하세요. (이슈명은 slugify 하여 Topic ID로 사용. 예: `us_rate_hike`)
2. 각 이슈에 대해 가장 관련 있는 `세부자산군2` 항목들만 양방향으로 매핑하세요. 관련된 자산군에만 스코어를 산출합니다.

### Step 3: 분석 리포트 및 스코어 데이터 생성 (Multi-Pass)
에이전트는 내부적으로 다음 Part를 순차적으로 도출합니다.

*   **Part A (요약)**: 도출된 이슈들에 대한 핵심 매크로 현황 요약
*   **Part B (스코어링 테이블)**: 이슈별 자산 매핑 결과와 Direction, Horizon, Signal, Impact, 최종 WI(Weighted Impact) 테이블
*   **Part C (일별 종합 분석)**: 전체 이슈의 WI를 자산군별로 합산(Aggregate)하여 산출한 총 점수 순위
*   **Part D (액션 플랜 - 실행 가이드 & ETF 추천)**:
    *   당일 가중 영향도(|WI|)가 유의미한 **상위 3~5개 핵심 자산군**을 선별하여 비중 조절 방향(확대/축소/유지)을 제시합니다.
    *   **보유 ETF 매매 가이드**: 해당 자산군에 속한 실제 `holdings` 목록을 매핑하고, 매크로 연관성(섹터/테마 성격)을 1순위로 고려하되 현재 평가수익률(차익실현 또는 손실관리)과 비중을 종합 감안하여 구체적인 실행 액션(차익실현, 추가매수, 비중축소, 관망)과 근거를 작성합니다.
    *   **신규 도입 추천 상품**: 기존 보유 종목으로 커버되지 않는 매크로 기회가 있다면, 해당 자산군 내에서 새로 편입할 만한 유망 ETF/상품 및 추천 사유를 제안합니다.
*   **Part E (리스크 모니터링 - 취약 ETF & 시장 트리거)**:
    *   당일 거시경제 핵심 **리스크 요인 2~3개**를 도출합니다.
    *   **취약 보유 ETF 지목**: 해당 리스크 발생 시 가장 직접적 타격을 입을 수 있는 실제 보유 ETF를 지목하고 예상 파급효과를 설명합니다.
    *   **시장 트리거 지표**: 비중 축소나 방어(헤지) 액션을 실행해야 할 구체적인 시장 지표 기준(예: 미 10년물 국채금리 4.5% 돌파 시, 특정 유가/환율 레벨 등)을 명시합니다.

### Step 4: Archive 누적 저장 (Append/Merge)
오늘 날짜 기반으로 아카이브 폴더와 파일을 확인합니다. (예: `archive/2026-09/20260911_macro_analysis.json` 및 `.md`)

**1. JSON 데이터 병합**
*   파일이 이미 존재한다면 내용을 읽고 `topics` 배열을 확인합니다.
*   이번에 도출한 주제(Topic ID)가 이미 존재한다면 해당 객체의 스코어를 갱신(Update)하고, 없다면 `topics` 배열에 추가(Append)합니다.
*   `daily_summary` (Part C, D, E 데이터) 부분은 새롭게 병합된 전체 topics와 holdings 분석을 바탕으로 새로 계산하여 덮어씁니다.
*   **구조화된 포맷**:
    ```json
    {
      "date": "YYYY-MM-DD",
      "topics": [
        {
          "topic_id": "us_rate_cut_expectation",
          "part_a": "미국 금리 인하 기대감 확산 요약...",
          "part_b": [
            {
              "asset_class": "인덱스",
              "direction": 0.7,
              "horizon": 2,
              "signal": 0.8,
              "impact": 0.6,
              "weight": 20.5,
              "weighted_impact": 6.888
            }
          ]
        }
      ],
      "daily_summary": {
        "part_c": [
          { "asset_class": "인덱스", "total_wi": 6.89, "rank": 1 }
        ],
        "part_d": [
          {
            "asset_class": "인덱스",
            "action": "비중확대",
            "target_holdings": [
              {
                "name": "ACE미국S&P500",
                "action_type": "추가매수",
                "rationale": "시장 지수 상승 탄력 수혜 예상, 기존 비중 확대"
              }
            ],
            "new_recommendations": [
              {
                "name": "TIGER 미국테크TOP10",
                "rationale": "금리 하락기 대형 빅테크 랠리 동참을 위한 추가 편입 추천"
              }
            ]
          }
        ],
        "part_e": [
          {
            "risk_title": "미 인플레이션 재반등 및 매파적 금리 정책",
            "vulnerable_holdings": [
              {
                "name": "ACE미국30년국채액티브",
                "reason": "장기물 듀레이션 리스크 노출로 금리 반등 시 가격 하락 위험"
              }
            ],
            "trigger_indicator": "미 10년물 국채금리 4.40% 상향 돌파 시 장기채 비중 20% 축소"
          }
        ]
      }
    }
    ```

**2. MD 리포트 병합**
*   MD 리포트는 다음 구조로 누적/갱신됩니다.
    ```markdown
    # Daily Macro-Portfolio Analysis (YYYY-MM-DD)
    
    ## [주제별 분석]
    ### Topic: [이슈명1]
    (Part A 요약 및 Part B 스코어 테이블)
    
    ### Topic: [이슈명2] (새로 분석된 내용 Append)
    (Part A 요약 및 Part B 스코어 테이블)
    
    ---
    ## [일별 종합 분석] (이 영역은 전체 주제 취합 후 항상 덮어쓰기 Update)
    ### 종합 점수 (Part C)
    | 순위 | 세부자산군2 | 종합 WI |
    |---|---|---|
    ...
    
    ### 액션 플랜 (Part D)
    #### 1. [세부자산군2] - [비중확대/축소/유지]
    - **보유 ETF 조절 가이드**:
      * `[보유ETF명]` ([액션타입]): [매크로 연관성 및 손익/비중을 고려한 사유]
    - **신규 추천 상품**:
      * `[추천ETF명]`: [신규 편입 추천 사유]
      
    ### 리스크 요인 및 트리거 (Part E)
    #### 1. [리스크 요인명]
    - **취약 보유 ETF**: `[보유ETF명]` - [취약 원인 및 예상 영향]
    - **모니터링 지표 & 트리거**: [방어/축소 실행 기준 지표]
    ```

**3. 파일 쓰기 완료**
*   병합된 내용으로 `archive/` 디렉토리에 파일을 쓰고 사용자에게 요약 결과를 보고합니다.

> [!NOTE]
> Step 5 (Notion 업로드)는 당분간 보류 상태입니다. (향후 general 스킬로 연동 예정)
