from aiogram.fsm.state import State, StatesGroup

class OrderFlow(StatesGroup):
    waiting_for_order = State()
    waiting_for_confirmation = State()
    waiting_for_edit = State()
class ReminderFlow(StatesGroup):
    waiting_for_reminder = State()
class RetrieveFlow(StatesGroup):
    waiting_for_tab_choice = State() # שלב א': בחירת הטאב
    waiting_for_search_query = State() # שלב ב': הזנת השאלה החופשית
class PlanningFlow(StatesGroup):
    waiting_for_plan = State()          # המשתמש מקליד הודעה ראשונית
    waiting_for_confirmation = State() # המשתמש צריך ללחוץ: אישור / עריכה / ביטול
    waiting_for_edit = State()         # המשתמש מקליד טקסט לתיקון/הוספת מידע
class AdditionalHoursFlow(StatesGroup):
    waiting_for_hours = State()         # המשתמש מקליד הודעה ראשונית
    waiting_for_confirmation = State() # המשתמש צריך ללחוץ: אישור / עריכה / ביטול
    waiting_for_edit = State()         # המשתמש מקליד טקסט לתיקון/הוספת מידע
class DailySummaryFlow(StatesGroup):
    waiting_for_file_or_text = State() # מחכה לקובץ או טקסט חופשי מהעובד
    waiting_for_confirmation = State() # תפריט אישור/עריכה/ביטול