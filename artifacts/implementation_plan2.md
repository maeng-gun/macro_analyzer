# Macro-Portfolio Cross-Analyzer — 구현 계획서

글로벌 매크로 경제 분석 에이전트를 구축합니다. 매일 수집되는 매크로 리포트/뉴스를 파싱하고, Supabase의 포트폴리오 데이터와 교차 분석하여 정량 스코어(Direction, Signal, Impact)를 산출, Weighted Impact를 통해 개인화된 투자 인사이트를 도출합니다.

> [!IMPORTANT]
> 이 계획은 3번의 `/grill-me` 인터뷰 라운드를 거쳐 확정된 요구사항 및 설계 결정을 기반으로 작성되었습니다.

## 확정된 설계 결정 (인터뷰 반영)

| 카테고리 | 항목 | 결정 내용 |
| :--- | :--- | :--- |
| **운영 환경** | 실행 환경 | 로컬 Antigravity IDE/CLI 수동 트리거 (향후 SDK 웹 앱 확장 고려) |
| | 프레임워크 | `AGENTS.md` + `SKILL.md` 기반 오케스트레이션 |
| | 크롤링/Notion | 당분간 보류. URL 크롤링 제외, Notion 연동은 Placeholder만 기재. |
| **데이터 연동** | Supabase 호출 | `supabase-py` (공식 파이썬 클라이언트) 활용 |
| **스코어링** | Horizon | Weighted Impact(WI) 계산에서 **제외**. 리포트 내 필터링/정렬 참고용으로만 사용 |
| | Direction | 9단계 이산값 **[-1.0, -0.7, -0.5, -0.3, 0.0, +0.3, +0.5, +0.7, +1.0]** |
| | Signal / Impact | 0.1 단위 유지 **[0.0, 0.1, ..., 1.0]** |
| | 매핑 전략 | 양방향 매핑 (이슈 추출 후 관련된 세부자산군2 에만 선택적 매핑) |
| **에이전트 로직** | 리포트 생성 방식 | Multi-pass (Part A → Part B → Part C/D/E 순차적 프롬프트 수행) |
| **아카이빙 구조** | 파일 형태 | `YYYYMMDD_macro_analysis.json` (단일 파일), `YYYYMMDD_macro_analysis.md` (단일 파일) |
| (핵심) | 누적/갱신(Merge) | - **JSON**: `topics[]` 배열에 새 주제 객체 추가 (Slug ID 일치 시 Score Update)<br>- **MD**: Part A, B는 주제별로 기존 내용 하단에 Append. Part C, D, E는 전체 통합하여 갱신(Update) |
| | 주제 식별 기준 | 에이전트가 자동 판단하여 그룹핑 후 영문 슬러그화 (예: `us_rate_hike`) |

---

## Proposed Changes

### 1. 프로젝트 기반 구조 (Python + Env)

#### [NEW] pyproject.toml
- Python 프로젝트 메타데이터 정의
- 필수 패키지: `pdfplumber`, `supabase`, `python-dotenv`

#### [NEW] .env.example
- `SUPABASE_URL`, `SUPABASE_KEY` 설정 템플릿

#### [NEW] Directories
- `input_staging/` : 분석 대상 파일 (PDF, TXT, MD) 적재 위치
- `scratch/` : 파이프라인 중간 산출물 보관 위치
- `archive/` : 최종 분석 결과 (JSON, MD) 보관 위치

### 2. Python 스크립트 (Data Ingestion)

#### [NEW] src/scripts/parse_all_inputs.py
- `input_staging/` 내의 파일(pdf, txt, md)을 모두 읽어 `scratch/parsed_report_YYYYMMDD.md` 하나로 병합.

#### [NEW] src/scripts/fetch_portfolio.py
- Supabase에 연결하여 `asset_ratio`, `holdings`, `groups` 데이터를 조회.
- 현재 자산군별 비중(Weight) 정보를 `scratch/portfolio_snapshot_YYYYMMDD.json`에 저장.

### 3. 에이전트 설정 (Persona & Workflow)

#### [NEW] AGENTS.md
- 페르소나 설정: 글로벌 매크로 분석가 및 TAA 관리자
- 4차원 스코어링 공식 정의 (Direction, Horizon, Signal, Impact의 범위 명시)
- Weighted Impact 공식: `WI = Direction * Signal * Impact * Weight`

#### [NEW] .agents/skills/macro_portfolio_analysis/SKILL.md
- 에이전트가 따라야 할 Step 1~4 상세 워크플로우 정의.
- **Merge/Append 지침**:
  - `archive/` 에 당일 날짜 파일이 있는지 확인.
  - 있다면 읽어와서 파싱된 이슈(Topic)와 대조.
  - 슬러그 ID가 일치하면 Update, 없으면 Append 처리 (JSON 및 MD 구조에 맞게 반영).
- **Multi-pass 생성 지침**: Part A(요약) -> Part B(스코어 테이블) -> Part C/D/E(종합 분석 및 리스크) 순서로 생성.

### 4. 출력물 템플릿 구조

- **MD 아카이브 파일 구조**:
  ```markdown
  # Daily Macro-Portfolio Analysis (YYYY-MM-DD)

  ## [주제별 분석] (Append 영역)
  ### Topic 1: [이슈명]
  - Part A 요약 내용...
  - Part B 스코어 테이블...
  
  ### Topic 2: [이슈명] (새로 추가됨)
  ...
  
  ---
  ## [일별 종합 분석] (Update 영역)
  - Part C: 종합 점수 및 상위/하위 자산
  - Part D: 액션 플랜
  - Part E: 리스크 모니터링
  ```
- **JSON 아카이브 구조**: `{"date": "YYYY-MM-DD", "topics": [{...}], "daily_summary": {...}}`

---

## Verification Plan

### 1. 자동 검증 (단위 테스트)
- `parse_all_inputs.py` 실행 → `scratch/` 에 병합된 md 텍스트 생성 확인
- `fetch_portfolio.py` 실행 → `scratch/` 에 포트폴리오 비중 json 데이터 생성 확인

### 2. E2E 테스트 (샘플 데이터 기반)
1. `input_staging/` 에 샘플 매크로 리포트 파일 투입.
2. 메인 에이전트 스킬 실행 (`Step 1 ~ Step 4`).
3. `archive/` 내에 당일 MD, JSON 파일 정상 생성 확인.
4. **동일 일자 재실행 테스트**: 새로운 샘플 파일을 `input_staging/` 에 넣고 다시 실행.
5. `archive/` 내 기존 파일에 주제가 정상적으로 Append 되고, 종합 분석(Part C,D,E)이 갱신(Update)되는지 검증.
