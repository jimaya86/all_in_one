import flet as ft
import time
import datetime
import webbrowser
import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# [보안] .env 파일에서 클라우드 DB 접속 주소 로드
load_dotenv()
DB_URL = os.environ.get("SUPABASE_DB_URL")

if not DB_URL:
    print("[경고] .env 파일에 SUPABASE_DB_URL이 설정되지 않았습니다.")


# [모듈 1] 클라우드 데이터베이스 연결 및 문제 조회 엔진
def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=psycopg2.extras.DictCursor)


def get_random_question(topic_id=None):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if topic_id:
            cursor.execute("""
                           SELECT q.*, t."Topic_Name"
                           FROM questions q
                                    LEFT JOIN topics t ON q."Topic_ID" = t."ID"
                           WHERE q."Topic_ID" = %s
                           ORDER BY RANDOM() LIMIT 1
                           """, (topic_id,))
        else:
            cursor.execute("""
                           SELECT q.*, t."Topic_Name"
                           FROM questions q
                                    LEFT JOIN topics t ON q."Topic_ID" = t."ID"
                           ORDER BY RANDOM() LIMIT 1
                           """)

        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[시스템] 랜덤 문제 조회 실패: {e}")
        return None


def get_review_question(nickname):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
                       SELECT q.*, t."Topic_Name"
                       FROM questions q
                                LEFT JOIN topics t ON q."Topic_ID" = t."ID"
                                JOIN solve_history h ON q."ID" = h.question_id
                       WHERE h.session_id = %s
                         AND h.is_correct = 0
                       ORDER BY RANDOM() LIMIT 1
                       """, (nickname,))

        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[시스템] 복습 문제 조회 실패: {e}")
        return None


# [모듈 2] 학습 이력 클라우드 DB 저장 및 제어 엔진
def save_solve_history(nickname, q_id, user_answer, is_correct, elapsed_time):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_taken_int = int(elapsed_time)
        cursor.execute(
            "INSERT INTO solve_history (question_id, user_answer, is_correct, solved_at, time_taken, session_id) VALUES (%s, %s, %s, %s, %s, %s)",
            (q_id, user_answer, is_correct, now, time_taken_int, nickname)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[시스템] 학습 이력 저장 실패: {e}")


def auto_clean_history(nickname, days=30):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM solve_history WHERE session_id = %s AND solved_at < NOW() - INTERVAL '{days} days'",
            (nickname,)
        )
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        if deleted_count > 0:
            print(f"[시스템] {days}일 경과 데이터 자동 삭제 완료 ({deleted_count}건)")
    except Exception as e:
        print(f"[시스템] 자동 초기화 실패: {e}")


def clear_all_history(nickname):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM solve_history WHERE session_id = %s", (nickname,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[시스템] 수동 초기화 실패: {e}")


# [모듈 3] 문제 신고 클라우드 DB 저장 엔진
def save_report(q_id, nickname, reason):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO reports (question_id, session_id, comment, reported_at) VALUES (%s, %s, %s, %s)",
            (q_id, nickname, reason, now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[시스템] 문제 신고 저장 실패: {e}")


# [모듈 4] 토픽별 학습 통계 조회 엔진
def get_topic_statistics(nickname):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
                       SELECT q."Topic_ID",
                              t."Topic_Name",
                              COUNT(*)          as total_attempts,
                              SUM(h.is_correct) as correct_attempts
                       FROM solve_history h
                                JOIN questions q ON h.question_id = q."ID"
                                LEFT JOIN topics t ON q."Topic_ID" = t."ID"
                       WHERE h.session_id = %s
                       GROUP BY q."Topic_ID", t."Topic_Name"
                       ORDER BY (CAST(SUM(h.is_correct) AS FLOAT) / COUNT(*)) ASC, COUNT(*) DESC
                       """, (nickname,))
        rows = cursor.fetchall()
        conn.close()

        stats = []
        for row in rows:
            topic_id = row["Topic_ID"] if row["Topic_ID"] else 0
            topic_name = row["Topic_Name"] if row["Topic_Name"] else "미분류"
            total = row["total_attempts"]
            correct = row["correct_attempts"]
            accuracy = round((correct / total) * 100, 1) if total > 0 else 0
            stats.append({
                "topic_id": topic_id,
                "topic_name": topic_name,
                "total": total,
                "correct": correct,
                "accuracy": accuracy
            })
        return stats
    except Exception as e:
        print(f"[시스템] 통계 조회 실패: {e}")
        return []


# [모듈 5] 메인 컨트롤러 (웹 최적화)
def main(page: ft.Page):
    page.title = "올인원 필수암기 문제풀이"
    page.window.width = 450
    page.window.height = 800
    page.theme_mode = ft.ThemeMode.LIGHT

    def navigate(route_name):
        page.route = route_name
        page.views.clear()

        # --- 1. 진입 화면 (로그인) ---
        if route_name == "/":
            nickname_input = ft.TextField(label="닉네임 입력", width=300, hint_text="이름을 입력하세요.")

            def on_start(e):
                if nickname_input.value:
                    nick = nickname_input.value

                    # 브라우저 탭 단위의 독립 세션에만 닉네임 저장 (충돌 0%)
                    page.session.store.set("user_nickname", nick)

                    auto_clean_history(nick, days=30)
                    navigate("/home")
                else:
                    snack = ft.SnackBar(content=ft.Text("닉네임을 입력하세요."))
                    page.overlay.append(snack)
                    snack.open = True
                    page.update()

            page.views.append(ft.View(
                route="/",
                controls=[
                    ft.Icon(ft.Icons.MENU_BOOK, size=50, color="#2196F3"),
                    ft.Text("올인원 필수암기", size=30, weight=ft.FontWeight.BOLD),
                    ft.Container(height=20),
                    nickname_input,
                    ft.Text("※ 클라우드 서버 연동 완료. 데이터가 영구 보존됩니다.", size=12, color="#1976D2"),
                    ft.Container(height=20),
                    ft.Button(content=ft.Text("학습 시작하기"), on_click=on_start, width=300)
                ],
                vertical_alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ))

        # --- 2. 메인 홈 화면 ---
        elif route_name == "/home":
            nickname = page.session.store.get("user_nickname") or "학습자"
            page.views.append(ft.View(
                route="/home",
                controls=[
                    ft.Icon(ft.Icons.CLOUD_DONE, size=40, color="#4CAF50"),
                    ft.Container(height=10),
                    ft.Text(f"반갑습니다, {nickname}님! 👋", size=22, weight=ft.FontWeight.BOLD),
                    ft.Container(height=30),
                    ft.Button(content=ft.Text("🎲 전체 랜덤 문제 풀기"), on_click=lambda _: navigate("/random"), width=300),
                    ft.Button(content=ft.Text("🔄 스마트 오답 복습"), on_click=lambda _: navigate("/review"), width=300),
                    ft.Button(content=ft.Text("📊 취약점 진단 대시보드"), on_click=lambda _: navigate("/history"), width=300),
                    ft.Button(content=ft.Text("☕ 스터디 카페 가기"),
                              on_click=lambda _: webbrowser.open("https://cafe.naver.com/yjbooks"), width=300),
                ],
                vertical_alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ))

        # --- 3. 랜덤 문제 풀기 화면 ---
        elif route_name == "/random":
            nickname = page.session.store.get("user_nickname") or "학습자"
            target_topic_id = page.session.store.get("target_topic_id")

            q = get_random_question(target_topic_id)
            page.session.store.set("target_topic_id", None)

            if q:
                topic_name = q.get("Topic_Name", "미분류")
                appbar_title = f"집중 복습: {topic_name}" if target_topic_id else "랜덤 문제 풀기"
            else:
                appbar_title = "랜덤 문제 풀기"

            appbar = ft.AppBar(
                title=ft.Text(appbar_title, size=16, weight=ft.FontWeight.BOLD),
                actions=[ft.IconButton(icon=ft.Icons.HOME, on_click=lambda _: navigate("/home"), tooltip="홈으로 이동")],
                bgcolor="#F2F2F2"
            )

            if not q:
                page.views.append(ft.View(
                    route="/random",
                    appbar=appbar,
                    controls=[
                        ft.Icon(ft.Icons.WARNING, size=50, color="#F44336"),
                        ft.Text("해당 조건의 문제가 DB에 없습니다.", color="#F44336", weight=ft.FontWeight.BOLD)
                    ],
                    vertical_alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ))
            else:
                question_start_time = time.time()
                question_id = q.get("ID", 0)
                topic_id = q.get("Topic_ID", 0)
                explanation = q.get("Explanation", "등록된 해설이 없습니다.")

                def check_answer(e):
                    elapsed_time = round(time.time() - question_start_time, 2)
                    selected = e.control.data
                    correct = q["Ans"]
                    is_correct = 1 if selected == int(correct) else 0

                    save_solve_history(nickname, question_id, selected, is_correct, elapsed_time)

                    title_text = "🎉 정답입니다!" if is_correct else f"❌ 오답입니다. (정답: {correct}번)"
                    title_color = "#4CAF50" if is_correct else "#F44336"

                    def go_next(e):
                        result_dialog.open = False
                        page.update()
                        navigate("/random")

                    def go_similar(e):
                        result_dialog.open = False
                        page.session.store.set("target_topic_id", topic_id)
                        page.update()
                        navigate("/random")

                    result_dialog = ft.AlertDialog(
                        title=ft.Text(title_text, color=title_color, weight=ft.FontWeight.BOLD),
                        content=ft.Container(
                            content=ft.Column([
                                ft.Text(f"소요 시간: {elapsed_time}초", size=12, color="#757575"),
                                ft.Container(height=10),
                                ft.Text("📖 해설", weight=ft.FontWeight.BOLD),
                                ft.Text(explanation, size=14)
                            ], scroll=ft.ScrollMode.AUTO, tight=True),
                            height=250, width=350
                        ),
                        actions=[
                            ft.Button(content=ft.Text("같은 유형 계속 풀기"), on_click=go_similar),
                            ft.Button(content=ft.Text("다음 문제"), on_click=go_next)
                        ],
                        actions_alignment=ft.MainAxisAlignment.END
                    )
                    page.overlay.append(result_dialog)
                    result_dialog.open = True
                    page.update()

                def open_report_dialog(e):
                    reason_input = ft.TextField(label="신고 사유", multiline=True, width=300)

                    def submit_report(e):
                        if reason_input.value:
                            save_report(question_id, nickname, reason_input.value)
                            report_dialog.open = False
                            snack = ft.SnackBar(content=ft.Text("신고가 정상 접수되었습니다."), bgcolor="#4CAF50")
                            page.overlay.append(snack)
                            snack.open = True
                            page.update()

                    def close_report(e):
                        report_dialog.open = False
                        page.update()

                    report_dialog = ft.AlertDialog(
                        title=ft.Text("🚨 문제 오류 신고", weight=ft.FontWeight.BOLD),
                        content=ft.Column([
                            ft.Text("오탈자, 정답 오류 등을 기재해 주세요.", size=12),
                            reason_input
                        ], tight=True),
                        actions=[
                            ft.Button(content=ft.Text("취소"), on_click=close_report),
                            ft.Button(content=ft.Text("전송"), on_click=submit_report)
                        ]
                    )
                    page.overlay.append(report_dialog)
                    report_dialog.open = True
                    page.update()

                page.views.append(ft.View(
                    route="/random",
                    appbar=appbar,
                    controls=[
                        ft.Row([
                            ft.Text(f"현재 학습자: {nickname}", size=14, color="#1976D2", weight=ft.FontWeight.BOLD),
                            ft.IconButton(icon=ft.Icons.REPORT_PROBLEM, icon_color="#F44336",
                                          on_click=open_report_dialog, tooltip="문제 신고")
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=350),

                        ft.Container(height=10),
                        ft.Text(f"[{topic_name}]", size=12, color="#757575", weight=ft.FontWeight.BOLD),
                        ft.Text(f"Q. {q['Question']}", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(height=20),
                        ft.Button(content=ft.Text(f"1. {q['Opt1']}"), data=1, on_click=check_answer, width=350),
                        ft.Container(height=5),
                        ft.Button(content=ft.Text(f"2. {q['Opt2']}"), data=2, on_click=check_answer, width=350),
                        ft.Container(height=5),
                        ft.Button(content=ft.Text(f"3. {q['Opt3']}"), data=3, on_click=check_answer, width=350),
                        ft.Container(height=5),
                        ft.Button(content=ft.Text(f"4. {q['Opt4']}"), data=4, on_click=check_answer, width=350)
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ))

        # --- 4. 오답 복습 문제 풀기 화면 ---
        elif route_name == "/review":
            nickname = page.session.store.get("user_nickname") or "학습자"
            q = get_review_question(nickname)

            appbar = ft.AppBar(
                title=ft.Text("스마트 오답 복습", size=16, weight=ft.FontWeight.BOLD),
                actions=[ft.IconButton(icon=ft.Icons.HOME, on_click=lambda _: navigate("/home"), tooltip="홈으로 이동")],
                bgcolor="#FFEBEE"
            )

            if not q:
                page.views.append(ft.View(
                    route="/review",
                    appbar=appbar,
                    controls=[
                        ft.Icon(ft.Icons.STAR, size=60, color="#FFC107"),
                        ft.Container(height=10),
                        ft.Text("현재 복습할 오답이 없습니다!\n완벽합니다 🎉", text_align=ft.TextAlign.CENTER, size=18,
                                weight=ft.FontWeight.BOLD),
                        ft.Container(height=20),
                        ft.Button(content=ft.Text("메인으로 돌아가기"), on_click=lambda _: navigate("/home"), width=300)
                    ],
                    vertical_alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ))
            else:
                question_start_time = time.time()
                question_id = q.get("ID", 0)
                topic_name = q.get("Topic_Name", "미분류")
                explanation = q.get("Explanation", "등록된 해설이 없습니다.")

                def check_answer(e):
                    elapsed_time = round(time.time() - question_start_time, 2)
                    selected = e.control.data
                    correct = q["Ans"]
                    is_correct = 1 if selected == int(correct) else 0

                    save_solve_history(nickname, question_id, selected, is_correct, elapsed_time)

                    title_text = "🎉 정답입니다!" if is_correct else f"❌ 또 틀렸습니다. (정답: {correct}번)"
                    title_color = "#4CAF50" if is_correct else "#F44336"

                    def go_next_review(e):
                        result_dialog.open = False
                        page.update()
                        navigate("/review")

                    result_dialog = ft.AlertDialog(
                        title=ft.Text(title_text, color=title_color, weight=ft.FontWeight.BOLD),
                        content=ft.Container(
                            content=ft.Column([
                                ft.Text(f"소요 시간: {elapsed_time}초", size=12, color="#757575"),
                                ft.Container(height=10),
                                ft.Text("📖 해설", weight=ft.FontWeight.BOLD),
                                ft.Text(explanation, size=14)
                            ], scroll=ft.ScrollMode.AUTO, tight=True),
                            height=250, width=350
                        ),
                        actions=[
                            ft.Button(content=ft.Text("다음 오답 풀기"), on_click=go_next_review)
                        ],
                        actions_alignment=ft.MainAxisAlignment.END
                    )
                    page.overlay.append(result_dialog)
                    result_dialog.open = True
                    page.update()

                page.views.append(ft.View(
                    route="/review",
                    appbar=appbar,
                    controls=[
                        ft.Row([
                            ft.Text(f"현재 학습자: {nickname}", size=14, color="#D32F2F", weight=ft.FontWeight.BOLD),
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=350),

                        ft.Container(height=10),
                        ft.Text(f"[{topic_name}]", size=12, color="#757575", weight=ft.FontWeight.BOLD),
                        ft.Text(f"Q. {q['Question']}", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(height=20),
                        ft.Button(content=ft.Text(f"1. {q['Opt1']}"), data=1, on_click=check_answer, width=350),
                        ft.Container(height=5),
                        ft.Button(content=ft.Text(f"2. {q['Opt2']}"), data=2, on_click=check_answer, width=350),
                        ft.Container(height=5),
                        ft.Button(content=ft.Text(f"3. {q['Opt3']}"), data=3, on_click=check_answer, width=350),
                        ft.Container(height=5),
                        ft.Button(content=ft.Text(f"4. {q['Opt4']}"), data=4, on_click=check_answer, width=350)
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ))

        # --- 5. 취약점 진단 대시보드 화면 ---
        elif route_name == "/history":
            nickname = page.session.store.get("user_nickname") or "학습자"
            stats_data = get_topic_statistics(nickname)

            def open_reset_dialog(e):
                def do_reset(e):
                    clear_all_history(nickname)
                    reset_dialog.open = False
                    page.update()
                    navigate("/history")
                    snack = ft.SnackBar(content=ft.Text("학습 이력이 모두 초기화되었습니다."), bgcolor="#4CAF50")
                    page.overlay.append(snack)
                    snack.open = True
                    page.update()

                def cancel_reset(e):
                    reset_dialog.open = False
                    page.update()

                reset_dialog = ft.AlertDialog(
                    title=ft.Text("⚠️ 이력 전체 초기화", weight=ft.FontWeight.BOLD),
                    content=ft.Text("정말로 모든 학습 이력을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없으며, 통계가 모두 초기화됩니다."),
                    actions=[
                        ft.Button(content=ft.Text("취소"), on_click=cancel_reset),
                        ft.Button(content=ft.Text("초기화", color="#F44336"), on_click=do_reset)
                    ]
                )
                page.overlay.append(reset_dialog)
                reset_dialog.open = True
                page.update()

            appbar = ft.AppBar(
                title=ft.Text("취약점 진단 대시보드", weight=ft.FontWeight.BOLD),
                actions=[
                    ft.IconButton(icon=ft.Icons.DELETE_FOREVER, icon_color="#F44336", on_click=open_reset_dialog,
                                  tooltip="이력 초기화"),
                    ft.IconButton(icon=ft.Icons.HOME, on_click=lambda _: navigate("/home"), tooltip="홈으로 이동")
                ],
                bgcolor="#F2F2F2"
            )

            if not stats_data:
                page.views.append(ft.View(
                    route="/history",
                    appbar=appbar,
                    controls=[
                        ft.Icon(ft.Icons.INFO, size=50, color="#1976D2"),
                        ft.Text(f"{nickname}님의 학습 데이터가 부족합니다.", weight=ft.FontWeight.BOLD),
                        ft.Container(height=20),
                        ft.Button(content=ft.Text("데이터 쌓으러 가기"), on_click=lambda _: navigate("/random"), width=300)
                    ],
                    vertical_alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ))
            else:
                total_all = sum(item["total"] for item in stats_data)
                correct_all = sum(item["correct"] for item in stats_data)
                accuracy_all = round((correct_all / total_all) * 100, 1) if total_all > 0 else 0

                summary_card = ft.Container(
                    content=ft.Row([
                        ft.Text(f"누적 {total_all}문제", weight=ft.FontWeight.BOLD),
                        ft.Text(f"종합 정답률 {accuracy_all}%", color="#2196F3", weight=ft.FontWeight.BOLD),
                    ], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                    padding=15, bgcolor="#E3F2FD", border_radius=10, width=400
                )

                topic_list = ft.ListView(expand=True, spacing=10, width=400)

                def start_topic_review(e, target_topic_id):
                    page.session.store.set("target_topic_id", target_topic_id)
                    navigate("/random")

                for item in stats_data:
                    acc = item["accuracy"]
                    is_weak = acc < 60
                    card_bgcolor = "#FFEBEE" if is_weak else "#FFFFFF"
                    acc_color = "#D32F2F" if is_weak else "#388E3C"

                    record_card = ft.Container(
                        content=ft.Column([
                            ft.Text(f"[{item['topic_name']}]", size=16, weight=ft.FontWeight.BOLD),
                            ft.Text(f"정답률 {acc}%", color=acc_color, weight=ft.FontWeight.BOLD, size=15),
                            ft.Container(height=5),
                            ft.Row([
                                ft.Text(f"풀이: {item['total']}회 / 정답: {item['correct']}회", size=12, color="#616161"),
                                ft.Button(
                                    content=ft.Text("집중 복습", size=12, color="#FFFFFF"),
                                    bgcolor="#1976D2",
                                    on_click=lambda e, t=item['topic_id']: start_topic_review(e, t)
                                )
                            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
                        ]),
                        padding=15,
                        bgcolor=card_bgcolor,
                        border=ft.Border.all(1, "#E0E0E0"),
                        border_radius=8
                    )
                    topic_list.controls.append(record_card)

                page.views.append(ft.View(
                    route="/history",
                    appbar=appbar,
                    controls=[
                        ft.Text("정답률이 낮은 취약 토픽이 상단에 표시됩니다.", size=12, color="#F44336", weight=ft.FontWeight.BOLD),
                        ft.Container(height=10),
                        summary_card,
                        ft.Container(height=10),
                        topic_list
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                ))

        page.update()

    def view_pop(e):
        navigate("/home")

    page.on_view_pop = view_pop
    navigate("/")


if __name__ == "__main__":
    ft.run(main)