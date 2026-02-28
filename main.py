import os
import flet as ft
import sqlite3
import random
import time
from datetime import datetime


# ==========================================
# 1. 서버(SQLite) DB 접근 영역 (문제, 토픽, 신고)
# ==========================================

def init_db():
    # 학습 이력은 세션에 저장하므로, 여기서는 초기화가 필요한 서버 테이블만 관리합니다.
    pass


def get_random_question():
    conn = sqlite3.connect('jima_study.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row


def get_same_topic_question(current_id, topic_id):
    conn = sqlite3.connect('jima_study.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions WHERE Topic_ID = ? AND ID != ? ORDER BY RANDOM() LIMIT 1",
                   (topic_id, current_id))
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT * FROM questions WHERE ID = ?", (current_id,))
        row = cursor.fetchone()
    conn.close()
    return row


def get_random_question_by_topic(topic_id):
    conn = sqlite3.connect('jima_study.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM questions WHERE Topic_ID = ? ORDER BY RANDOM() LIMIT 1", (topic_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def save_report(question_id, user_comment):
    conn = sqlite3.connect('jima_study.db')
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, question_id INTEGER, comment TEXT, reported_at DATETIME DEFAULT (DATETIME('now', 'localtime')))")
    cursor.execute("INSERT INTO reports (question_id, comment) VALUES (?, ?)", (question_id, user_comment))
    conn.commit()
    conn.close()


# ==========================================
# 2. 클라이언트 세션(page 인스턴스) 접근 영역 (학습 이력)
# ==========================================

def get_history(page: ft.Page):
    # page 객체에 solve_history 속성이 없으면 빈 리스트로 초기화하여 반환합니다.
    if not hasattr(page, "solve_history"):
        page.solve_history = []
    return page.solve_history


def save_history(page: ft.Page, q_id, user_ans, is_correct, duration):
    history = get_history(page)
    history.append({
        "question_id": q_id,
        "user_answer": user_ans,
        "is_correct": 1 if is_correct else 0,
        "solved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "time_taken": duration
    })


def get_topic_accuracy(page: ft.Page, topic_id):
    history = get_history(page)

    conn = sqlite3.connect('jima_study.db')
    conn.row_factory = sqlite3.Row
    q_rows = conn.execute("SELECT ID FROM questions WHERE Topic_ID = ?", (topic_id,)).fetchall()
    conn.close()

    target_q_ids = {row['ID'] for row in q_rows}
    total_attempts = 0
    correct_attempts = 0
    now = datetime.now()

    for r in history:
        if r['question_id'] in target_q_ids:
            solved_dt = datetime.strptime(r['solved_at'], "%Y-%m-%d %H:%M:%S")
            if (now - solved_dt).days <= 7:
                total_attempts += 1
                correct_attempts += r['is_correct']

    if total_attempts == 0:
        return f"[ 처음 풀어보는 유형 🌱 ]"

    accuracy = int((correct_attempts / total_attempts) * 100)
    return f"[ 유형별 정답률(7일 간): {accuracy}% ]"


def get_overall_stats(page: ft.Page):
    history = get_history(page)
    total_solved = len(history)
    total_correct = sum(r['is_correct'] for r in history)
    total_time = sum(r['time_taken'] for r in history)

    accuracy = int((total_correct / total_solved) * 100) if total_solved > 0 else 0
    return total_solved, accuracy, total_time


def get_topic_stats(page: ft.Page):
    history = get_history(page)

    conn = sqlite3.connect('jima_study.db')
    conn.row_factory = sqlite3.Row
    topics = conn.execute("SELECT ID, Topic_Name FROM topics").fetchall()
    questions = conn.execute("SELECT ID, Topic_ID FROM questions").fetchall()
    conn.close()

    q_to_t = {q['ID']: q['Topic_ID'] for q in questions}
    t_names = {t['ID']: t['Topic_Name'] for t in topics}

    stats_dict = {}
    for r in history:
        q_id = r['question_id']
        t_id = q_to_t.get(q_id)
        if not t_id: continue

        if t_id not in stats_dict:
            stats_dict[t_id] = {"total": 0, "correct": 0}

        stats_dict[t_id]["total"] += 1
        stats_dict[t_id]["correct"] += r["is_correct"]

    result = []
    for t_id, data in stats_dict.items():
        acc = int((data["correct"] / data["total"]) * 100) if data["total"] > 0 else 0
        result.append({
            "topic_id": t_id,
            "topic_name": t_names.get(t_id, "알 수 없는 유형"),
            "total_solved": data["total"],
            "accuracy": acc
        })

    result.sort(key=lambda x: x['accuracy'])
    return result


def get_review_question(page: ft.Page):
    history = get_history(page)
    if not history: return None

    latest_history = {}
    for r in history:
        q_id = r['question_id']
        r_time = datetime.strptime(r['solved_at'], "%Y-%m-%d %H:%M:%S")
        if q_id not in latest_history or r_time > latest_history[q_id]['dt']:
            latest_history[q_id] = {'data': r, 'dt': r_time}

    now = datetime.now()
    scored_questions = []

    for q_id, val in latest_history.items():
        r = val['data']
        dt = val['dt']
        score = 0

        if r['is_correct'] == 0: score += 50

        days_passed = (now - dt).days
        if days_passed >= 30:
            score += 50
        elif days_passed >= 14:
            score += 40
        elif days_passed >= 7:
            score += 30
        elif days_passed >= 3:
            score += 20
        elif days_passed >= 1:
            score += 10

        if r['time_taken'] >= 30: score += 10

        scored_questions.append((score, q_id))

    if not scored_questions: return None

    scored_questions.sort(key=lambda x: (x[0], random.random()), reverse=True)
    target_q_id = scored_questions[0][1]

    conn = sqlite3.connect('jima_study.db')
    conn.row_factory = sqlite3.Row
    q_data = conn.execute("SELECT * FROM questions WHERE ID = ?", (target_q_id,)).fetchone()
    conn.close()
    return q_data


def clear_history(page: ft.Page):
    # 페이지 객체 내의 리스트를 비워 완벽하게 초기화
    page.solve_history = []


# ==========================================
# 3. Flet UI 및 메인 로직
# ==========================================

async def main(page: ft.Page):
    page.title = "정보처리기사 지마쌤 All-In-One"
    page.window.width = 450
    page.window.height = 800

    # ColorScheme을 활용한 시맨틱 테마 전역 설정
    page.theme = ft.Theme(
        color_scheme=ft.ColorScheme(
            primary=ft.Colors.BLUE,
            on_primary=ft.Colors.ON_PRIMARY,
            error=ft.Colors.ERROR,
            on_error=ft.Colors.ON_ERROR,
            on_surface_variant=ft.Colors.ON_SURFACE_VARIANT,
            outline_variant=ft.Colors.OUTLINE_VARIANT,
            tertiary=ft.Colors.TEAL,
            on_tertiary=ft.Colors.ON_TERTIARY
        )
    )

    async def nav_to_random(e):
        await page.push_route("/random")

    async def nav_to_review(e):
        await page.push_route("/review")

    async def nav_to_history(e):
        await page.push_route("/history")

    async def nav_to_cafe(e):
        await page.launch_url("https://cafe.naver.com/yjbooks")

    async def nav_to_home(e):
        await page.push_route("/")

    # --- 홈 화면 뷰 ---
    def create_home_view():
        return ft.View(
            route="/",
            appbar=ft.AppBar(title=ft.Text("지마쌤 All-In-One"), bgcolor=ft.Colors.SURFACE_BRIGHT),
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            vertical_alignment=ft.MainAxisAlignment.CENTER,
            controls=[
                ft.Column([
                    ft.Button("🎲 랜덤 문제 풀이", width=300, on_click=nav_to_random),
                    ft.Button("🔄 복습 문제 풀이", width=300, on_click=nav_to_review),
                    ft.Button("📊 학습이력 관리", width=300, on_click=nav_to_history),
                    ft.Button("☕ 스터디 카페 가기", width=300, on_click=nav_to_cafe),
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    expand=True)
            ]
        )

    # --- 랜덤 문제 풀이 뷰 ---
    def create_random_quiz_view(q_data=None):
        if q_data is None:
            q_data = get_random_question()
        start_time = time.time()

        if not q_data:
            return ft.View(
                route="/random",
                appbar=ft.AppBar(title=ft.Text("랜덤 문제 풀이"),
                                 leading=ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=nav_to_home)),
                controls=[ft.Text("데이터베이스에 문제가 없습니다. DB를 확인해 주세요.")]
            )

        q_id = q_data['ID']
        topic_id = q_data['Topic_ID']
        question_text = q_data['Question']
        options = [q_data['Opt1'], q_data['Opt2'], q_data['Opt3'], q_data['Opt4']]
        answer = q_data['Ans']
        explanation = q_data['Explanation']

        accuracy_str = get_topic_accuracy(page, topic_id)
        accuracy_display = ft.Text(accuracy_str, color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD)

        result_text = ft.Text(size=18, weight=ft.FontWeight.BOLD)
        explanation_text = ft.Text(visible=False, color=ft.Colors.ON_SURFACE_VARIANT)

        async def next_question_click(e):
            page.views.pop()
            page.views.append(create_random_quiz_view())
            page.update()

        async def same_topic_click(e):
            same_q = get_same_topic_question(q_id, topic_id)
            page.views.pop()
            page.views.append(create_random_quiz_view(q_data=same_q))
            page.update()

        action_buttons = ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Button("다음 문제 ➡️", on_click=next_question_click),
                        ft.Button("같은 유형 더 풀기 🔄", on_click=same_topic_click)
                    ],
                    alignment=ft.MainAxisAlignment.CENTER
                ),
                ft.Button("🏠 첫 화면으로 돌아가기", on_click=nav_to_home, width=350)
            ],
            visible=False,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        opt_buttons = []

        async def option_click(e):
            selected_idx = e.control.data
            duration = int(time.time() - start_time)
            is_correct = (selected_idx == answer)

            save_history(page, q_id, selected_idx, is_correct, duration)

            for btn in opt_buttons:
                btn.disabled = True
                if btn.data == answer:
                    btn.bgcolor = ft.Colors.TERTIARY
                    btn.color = ft.Colors.ON_TERTIARY
                elif btn.data == selected_idx and not is_correct:
                    btn.bgcolor = ft.Colors.ERROR
                    btn.color = ft.Colors.ON_ERROR

            result_text.value = "🎉 정답입니다!" if is_correct else "💦 오답입니다."
            result_text.color = ft.Colors.TERTIARY if is_correct else ft.Colors.ERROR
            explanation_text.value = f"💡 해설: {explanation}" if explanation else "💡 해설: 등록된 해설이 없습니다."

            explanation_text.visible = True
            action_buttons.visible = True
            page.update()

        report_tf = ft.TextField(label="오류 내용이나 의견을 적어주세요.", multiline=True, max_lines=3)

        def submit_report(e):
            if report_tf.value:
                save_report(q_id, report_tf.value)
                report_tf.value = ""
                page.pop_dialog()
                page.show_dialog(ft.SnackBar(ft.Text("신고가 성공적으로 접수되었습니다. 감사합니다!")))
                page.update()

        def close_dialog(e):
            page.pop_dialog()
            page.update()

        report_dialog = ft.AlertDialog(
            title=ft.Text("문제 신고하기"),
            content=report_tf,
            actions=[
                ft.Button("취소", on_click=close_dialog),
                ft.Button("제출", on_click=submit_report, style=ft.ButtonStyle(color=ft.Colors.PRIMARY)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def open_report_dialog(e):
            page.show_dialog(report_dialog)
            page.update()

        for i, opt_text in enumerate(options, start=1):
            btn = ft.Button(
                f"{i}. {opt_text}",
                data=i,
                width=350,
                style=ft.ButtonStyle(alignment=ft.Alignment.CENTER_LEFT),
                on_click=option_click
            )
            opt_buttons.append(btn)

        return ft.View(
            route="/random",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            appbar=ft.AppBar(
                title=ft.Text("랜덤 문제 풀이"),
                leading=ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=nav_to_home),
                actions=[
                    ft.IconButton(icon=ft.Icons.REPORT_PROBLEM_OUTLINED, on_click=open_report_dialog,
                                  tooltip="문제 오류 신고")
                ]
            ),
            controls=[
                ft.Container(height=30),
                accuracy_display,
                ft.Text(f"Q. {question_text}", size=20, weight=ft.FontWeight.BOLD, width=350),
                ft.Container(height=20),
                *opt_buttons,
                ft.Container(height=20),
                result_text,
                explanation_text,
                ft.Container(height=20),
                action_buttons
            ]
        )

    # --- 복습 문제 풀이 뷰 ---
    def create_review_quiz_view(q_data=None):
        if q_data is None:
            q_data = get_review_question(page)

        start_time = time.time()

        if not q_data:
            return ft.View(
                route="/review",
                appbar=ft.AppBar(title=ft.Text("복습 문제 풀이"),
                                 leading=ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=nav_to_home)),
                controls=[
                    ft.Container(height=50),
                    ft.Text("아직 복습할 문제가 없습니다. 먼저 랜덤 문제를 풀어주세요!", weight=ft.FontWeight.BOLD)
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            )

        q_id = q_data['ID']
        topic_id = q_data['Topic_ID']
        question_text = q_data['Question']
        options = [q_data['Opt1'], q_data['Opt2'], q_data['Opt3'], q_data['Opt4']]
        answer = q_data['Ans']
        explanation = q_data['Explanation']

        accuracy_str = get_topic_accuracy(page, topic_id)
        accuracy_display = ft.Text(accuracy_str, color=ft.Colors.PRIMARY, weight=ft.FontWeight.BOLD)

        review_banner = ft.Container(
            content=ft.Text("🧠 망각 곡선 기반 복습 추천 문제", color=ft.Colors.ON_TERTIARY, weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.TERTIARY,
            padding=5,
            border_radius=3
        )

        result_text = ft.Text(size=18, weight=ft.FontWeight.BOLD)
        explanation_text = ft.Text(visible=False, color=ft.Colors.ON_SURFACE_VARIANT)

        async def next_review_click(e):
            page.views.pop()
            page.views.append(create_review_quiz_view())
            page.update()

        action_buttons = ft.Column(
            controls=[
                ft.Button("다음 복습 문제 ➡️", on_click=next_review_click),
                ft.Button("🏠 첫 화면으로 돌아가기", on_click=nav_to_home, width=350)
            ],
            visible=False,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER
        )
        opt_buttons = []

        async def option_click(e):
            selected_idx = e.control.data
            duration = int(time.time() - start_time)
            is_correct = (selected_idx == answer)

            save_history(page, q_id, selected_idx, is_correct, duration)

            for btn in opt_buttons:
                btn.disabled = True
                if btn.data == answer:
                    btn.bgcolor = ft.Colors.TERTIARY
                    btn.color = ft.Colors.ON_TERTIARY
                elif btn.data == selected_idx and not is_correct:
                    btn.bgcolor = ft.Colors.ERROR
                    btn.color = ft.Colors.ON_ERROR

            result_text.value = "🎉 완벽히 기억하셨네요!" if is_correct else "💦 아쉽게도 잊어버리셨군요. 다시 외워봅시다!"
            result_text.color = ft.Colors.TERTIARY if is_correct else ft.Colors.ERROR
            explanation_text.value = f"💡 해설: {explanation}" if explanation else "💡 해설: 등록된 해설이 없습니다."

            explanation_text.visible = True
            action_buttons.visible = True
            page.update()

        for i, opt_text in enumerate(options, start=1):
            btn = ft.Button(
                f"{i}. {opt_text}",
                data=i,
                width=350,
                style=ft.ButtonStyle(alignment=ft.Alignment.CENTER_LEFT),
                on_click=option_click
            )
            opt_buttons.append(btn)

        return ft.View(
            route="/review",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            appbar=ft.AppBar(
                title=ft.Text("복습 문제 풀이"),
                leading=ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=nav_to_home)
            ),
            controls=[
                ft.Container(height=10),
                review_banner,
                ft.Container(height=10),
                accuracy_display,
                ft.Text(f"Q. {question_text}", size=20, weight=ft.FontWeight.BOLD, width=350),
                ft.Container(height=20),
                *opt_buttons,
                ft.Container(height=20),
                result_text,
                explanation_text,
                ft.Container(height=20),
                action_buttons
            ]
        )

    # --- 학습이력 관리 뷰 ---
    def create_history_view():
        total_solved, accuracy, total_time = get_overall_stats(page)
        minutes = total_time // 60
        seconds = total_time % 60

        summary_text = ft.Text(
            f"📊 전체 푼 문제: {total_solved}개 | 누적 정답률: {accuracy}% | 총 학습 시간: {minutes}분 {seconds}초",
            weight=ft.FontWeight.BOLD,
            size=16
        )

        topic_stats = get_topic_stats(page)
        rows = []

        for stat in topic_stats:
            async def on_topic_click(e, tid=stat['topic_id']):
                q_data = get_random_question_by_topic(tid)
                if q_data:
                    page.views.pop()
                    page.views.append(create_random_quiz_view(q_data=q_data))
                    page.update()
                else:
                    page.show_dialog(ft.SnackBar(ft.Text("해당 유형에 아직 등록된 문제가 없습니다.")))
                    page.update()

            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(
                            ft.Container(
                                width=250,
                                content=ft.Button(
                                    stat['topic_name'],
                                    tooltip=stat['topic_name'],
                                    style=ft.ButtonStyle(
                                        alignment=ft.Alignment.CENTER_LEFT,
                                        padding=5,
                                        shape=ft.RoundedRectangleBorder(radius=5)
                                    ),
                                    on_click=on_topic_click
                                )
                            )
                        ),
                        ft.DataCell(ft.Text(str(stat['total_solved']))),
                        ft.DataCell(ft.Text(f"{stat['accuracy']}%")),
                    ]
                )
            )

        data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("유형명")),
                ft.DataColumn(ft.Text("푼 횟수"), numeric=True),
                ft.DataColumn(ft.Text("정답률"), numeric=True),
            ],
            rows=rows,
            width=400,
            column_spacing=15,
            horizontal_margin=10
        )

        # 공통 테두리 객체 정의
        outline_border = ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT)

        table_container = ft.Container(
            content=ft.Column([data_table], scroll=ft.ScrollMode.AUTO),
            height=400,
            border=ft.Border(
                top=outline_border,
                right=outline_border,
                bottom=outline_border,
                left=outline_border
            ),
            border_radius=5,
            padding=10
        )

        def confirm_clear(e):
            clear_history(page)
            page.pop_dialog()
            page.show_dialog(ft.SnackBar(ft.Text("학습 이력이 성공적으로 초기화되었습니다.")))
            page.views.pop()
            page.views.append(create_history_view())
            page.update()

        def cancel_clear(e):
            page.pop_dialog()
            page.update()

        clear_dialog = ft.AlertDialog(
            title=ft.Text("학습이력 초기화"),
            content=ft.Text("정말로 모든 학습 기록을 지우시겠습니까?\n이 작업은 되돌릴 수 없습니다."),
            actions=[
                ft.Button("취소", on_click=cancel_clear),
                ft.Button("초기화", style=ft.ButtonStyle(color=ft.Colors.ERROR), on_click=confirm_clear),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        def open_clear_dialog(e):
            page.show_dialog(clear_dialog)
            page.update()

        clear_btn = ft.Button(
            "⚠️ 학습이력 초기화",
            style=ft.ButtonStyle(color=ft.Colors.ERROR),
            on_click=open_clear_dialog
        )

        return ft.View(
            route="/history",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            appbar=ft.AppBar(
                title=ft.Text("학습이력 관리"),
                bgcolor=ft.Colors.SURFACE_BRIGHT,
                leading=ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=nav_to_home)
            ),
            controls=[
                ft.Container(height=20),
                summary_text,
                ft.Container(height=10),
                table_container,
                ft.Container(height=20),
                clear_btn
            ]
        )

    # --- 라우팅 컨트롤 로직 ---
    async def route_change(e):
        page.views.clear()
        page.views.append(create_home_view())

        if page.route == "/random":
            page.views.append(create_random_quiz_view())
        elif page.route == "/review":
            page.views.append(create_review_quiz_view())
        elif page.route == "/history":
            page.views.append(create_history_view())

        page.update()

    async def view_pop(e):
        page.views.pop()
        if page.views:
            top_view = page.views[-1]
            await page.push_route(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    # 초기 화면 렌더링
    await route_change(None)


if __name__ == "__main__":
    # Render 서버가 부여하는 PORT 환경변수를 가져오되, 로컬 테스트 시에는 8550을 사용합니다.
    port = int(os.environ.get("PORT", 8550))
    # host="0.0.0.0" 옵션은 외부망 접속을 허용하는 필수 웹 서버 설정입니다.

    ft.run(main, view=ft.AppView.WEB_BROWSER, port=port, host="0.0.0.0")
