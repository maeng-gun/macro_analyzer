# Macro-Portfolio Cross-Analyzer: holdings 연계 고도화 완료

사용자의 보유 종목(`holdings`)이 대부분 대표 인덱스/섹터 ETF라는 현실적 특성을 반영하여, 거시경제 분석 결과가 **실제 보유 ETF 단위의 실행 및 리스크 관리로 직결**되도록 워크플로우와 프롬프트 지침을 고도화했습니다.

---

## 1. 주요 변경 내용

### 1) 글로벌 에이전트 페르소나 및 원칙 ([AGENTS.md](file:///c:/Users/maeng-gun/Desktop/python/macro_analyzer/macro_analyzer/AGENTS.md))
* **핵심 임무 확장**:
  * 단순 자산군 비중 분석을 넘어, 사용자의 실제 보유 종목(`holdings`)을 매핑하여 구체적 매매 가이드 및 신규 편입 후보 ETF를 추천하는 임무 추가
  * 핵심 거시경제 리스크 요인에 가장 취약한 보유 ETF를 지목하고 시장 트리거 지표를 제시하는 임무 추가
* **보유 종목(ETF) 실행 원칙 (Part D)**:
  1. **매크로 부합도 우선**: 해당 자산군 내 보유 ETF 중 당일 매크로 이슈와 가장 직결되는 섹터/테마 ETF를 우선 조절 대상으로 선정
  2. **수익률 및 비중 감안**: 평가수익률(차익실현 vs 손실관리) 및 비중을 감안하여 현실적 액션(차익실현, 추가매수, 비중축소, 관망) 제시
  3. **신규 도입 상품 추천**: 기존 보유 ETF로 커버하기 어려운 매크로 기회 포착 시 유망 ETF/상품 신규 편입 제안
* **취약 종목 리스크 모니터링 원칙 (Part E)**:
  * 리스크 발생 시 타격이 가장 큰 실제 보유 ETF를 지목하고, 비중 축소나 방어를 검토할 구체적 시장 지표(금리, 환율, 원자재 레벨 등) 트리거 명시

---

### 2) 메인 분석 스킬 지침 ([SKILL.md](file:///c:/Users/maeng-gun/Desktop/python/macro_analyzer/macro_analyzer/.agents/skills/macro_portfolio_analysis/SKILL.md))
* **Step 1 (Ingestion)**: `portfolio_snapshot`에서 `holdings`를 `세부자산군2` 기준으로 그룹화/매핑하여 컨텍스트에 유지하도록 지침 추가
* **Step 3 (Part D & Part E 상세화)**:
  * **Part D (액션 플랜)**: 유의미한 상위 3~5개 핵심 자산군에 집중, 보유 ETF별 실행 가이드 + 신규 추천 ETF 도출
  * **Part E (리스크 모니터링)**: 핵심 리스크 2~3개 선정, 취약 보유 ETF 지목 + 방어 실행 시장 트리거 지표 제시
* **Step 4 (아카이브 포맷 고도화)**:
  * **JSON 아카이브 (`daily_summary`)**: `part_d`와 `part_e`를 구조화된 객체(JSON Array of Objects) 형태로 저장하도록 스키마 정의
  * **Markdown 리포트**: 표 및 가독성 높은 불릿 포인트 구조 템플릿 적용

---

### 3) 프로젝트 아키텍처 문서 동기화 ([Macro-Portfolio Cross-Analyzer.md](file:///c:/Users/maeng-gun/Desktop/python/macro_analyzer/macro_analyzer/Macro-Portfolio%20Cross-Analyzer.md))
* Step 3 교차 분석 설명에 보유 ETF 연계 분석 로직 반영
* Step 4 산출물 스펙에 구조화된 JSON 객체 정의 반영

---

## 2. 검증 결과

| 점검 항목 | 결과 | 내용 |
|---|---|---|
| **Supabase DB holdings 스키마 확인** | ✅ 통과 | 59개 보유 종목의 `자산군`, `세부자산군`, `세부자산군2`, `상품명`, `평가금액`, `평가수익률` 확인 완료 |
| **`asset_ratio` 및 `groups` 정합성** | ✅ 통과 | 18개 세부자산군2 및 계층 분류 구조와 `holdings`의 1:N 매핑 호환성 확인 |
| **AGENTS.md 규칙 정합성** | ✅ 통과 | 4차원 스코어링 + WI 공식 유지하면서 Part D/E 연계 원칙 보강 완료 |
| **SKILL.md 워크플로우 및 JSON 스키마** | ✅ 통과 | 상위 3~5개 자산군 집중 및 구조화된 JSON/MD 출력 양식 명세 완료 |
