"""아산시 홍보 사업 성과 분석 시스템 - 명령줄 진입점

사용법:
  python run.py daily              매일 실행: 수집 → 뉴스토어 → 이슈 통합 → 원문 확인 → 보고서(AI) → 내보내기
  python run.py collect            네이버 API HUB 뉴스 수집
  python run.py newstore [시작 끝]  뉴스토어(빅카인즈) API 기간 수집 (YYYY-MM-DD)
  python run.py bigkinds 파일.xlsx  빅카인즈 엑셀 가져오기
  python run.py cluster            유사 기사 → 이슈 통합
  python run.py views [최대건수]    원문 페이지에서 매체명·조회수 확인
  python run.py build              이슈 통합 + 통계(직전 AI 해석 재사용) + data.js 내보내기
  python run.py report             통계 + AI 해석 + data.js 내보내기
  python run.py sample             API 키 없이 샘플 데이터로 화면 만들기 (data/sample.db)
"""
import sys
import traceback

from asan_news import config, db


def _safe(name, fn, *a):
    try:
        return fn(*a)
    except SystemExit:
        print(f"[{name}] 건너뜀")
    except Exception:
        print(f"[{name}] 실패 - 다음 단계 계속 진행")
        traceback.print_exc()
    return None


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[1]
    config.load_env()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    from asan_news import bigkinds, cluster, collect, export, newstore, report, sample, views

    if cmd == "sample":
        conn = sample.run()
        cluster.run(conn)
        rep = report.build(conn, use_ai=False, sample=True)
        export.run(conn, rep, sample=True)
        return 0

    conn = db.connect()
    if cmd == "collect":
        collect.run(conn)
    elif cmd == "newstore":
        newstore.run(conn, *(argv[2:4]))
    elif cmd == "bigkinds":
        if len(argv) < 3:
            print("사용: python run.py bigkinds 파일.xlsx")
            return 1
        bigkinds.run(conn, argv[2])
    elif cmd == "cluster":
        cluster.run(conn)
    elif cmd == "views":
        views.run(conn, int(argv[2]) if len(argv) > 2 else None)
    elif cmd in ("build", "report"):
        cluster.run(conn)
        rep = report.build(conn, use_ai=(cmd == "report"))
        export.run(conn, rep)
    elif cmd == "daily":
        _safe("collect", collect.run, conn)
        _safe("newstore", newstore.run, conn)
        _safe("cluster", cluster.run, conn)
        _safe("views", views.run, conn)
        _safe("cluster", cluster.run, conn)  # 매체명 보정 반영
        rep = _safe("report", report.build, conn, True)
        if rep is not None:
            _safe("export", export.run, conn, rep)
        else:
            print("보고서 생성 실패 → 기존 data.js 유지")
    else:
        print(f"알 수 없는 명령: {cmd}\n")
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
