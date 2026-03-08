import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from gtts import gTTS
import os
import time
import sqlite3
import random
from datetime import datetime, timedelta

# محاولة استيراد مكتبات الرسم
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ================== الإعدادات الأساسية ==================
TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

admin_id = 8536981262  # ضع معرف المشرف

# ================== قاعدة البيانات ==================
conn = sqlite3.connect('toefl_master.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    name TEXT,
    current_day INTEGER DEFAULT 1,
    join_date DATE
)''')

c.execute('''CREATE TABLE IF NOT EXISTS progress (
    user_id INTEGER,
    day INTEGER,
    session TEXT,
    completed INTEGER DEFAULT 0,
    completed_at DATETIME,
    PRIMARY KEY (user_id, day, session)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS favorites (
    user_id INTEGER,
    word TEXT,
    meaning TEXT,
    example TEXT,
    level TEXT,
    PRIMARY KEY (user_id, word)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS daily_results (
    user_id INTEGER,
    day INTEGER,
    score INTEGER,
    total INTEGER,
    date DATE,
    PRIMARY KEY (user_id, day)
)''')

c.execute('''CREATE TABLE IF NOT EXISTS mastered (
    user_id INTEGER,
    word TEXT,
    mastered_level INTEGER DEFAULT 1,
    last_reviewed DATETIME,
    PRIMARY KEY (user_id, word)
)''')

conn.commit()

# ================== بيانات الكلمات - 30 يوم كاملة (480 كلمة) ==================
words_db = {
    1: {
        "morning": [
            ("book", "كتاب", "I read a book every night.", "مبتدئ"),
            ("door", "باب", "Please close the door.", "مبتدئ"),
            ("chair", "كرسي", "The chair is comfortable.", "مبتدئ"),
            ("table", "طاولة", "Put the book on the table.", "مبتدئ")
        ],
        "noon": [
            ("house", "منزل", "My house is big.", "مبتدئ"),
            ("car", "سيارة", "He drives a red car.", "مبتدئ"),
            ("water", "ماء", "I drink water.", "مبتدئ"),
            ("food", "طعام", "The food is delicious.", "مبتدئ")
        ],
        "afternoon": [
            ("big", "كبير", "A big house.", "مبتدئ"),
            ("small", "صغير", "A small cat.", "مبتدئ"),
            ("hot", "حار", "The weather is hot.", "مبتدئ"),
            ("cold", "بارد", "Cold water.", "مبتدئ")
        ],
        "night": [
            ("run", "يجري", "He runs fast.", "مبتدئ"),
            ("walk", "يمشي", "I walk to school.", "مبتدئ"),
            ("eat", "يأكل", "We eat dinner.", "مبتدئ"),
            ("sleep", "ينام", "She sleeps early.", "مبتدئ")
        ]
    },
    2: {
        "morning": [
            ("red", "أحمر", "Red apple.", "مبتدئ"),
            ("blue", "أزرق", "Blue sky.", "مبتدئ"),
            ("green", "أخضر", "Green grass.", "مبتدئ"),
            ("yellow", "أصفر", "Yellow sun.", "مبتدئ")
        ],
        "noon": [
            ("father", "أب", "My father is kind.", "مبتدئ"),
            ("mother", "أم", "My mother cooks.", "مبتدئ"),
            ("brother", "أخ", "I have a brother.", "مبتدئ"),
            ("sister", "أخت", "My sister is young.", "مبتدئ")
        ],
        "afternoon": [
            ("one", "واحد", "One apple.", "مبتدئ"),
            ("two", "اثنان", "Two cats.", "مبتدئ"),
            ("three", "ثلاثة", "Three books.", "مبتدئ"),
            ("four", "أربعة", "Four chairs.", "مبتدئ")
        ],
        "night": [
            ("hello", "مرحبا", "Hello, how are you?", "مبتدئ"),
            ("goodbye", "وداعا", "Goodbye, see you later.", "مبتدئ"),
            ("please", "من فضلك", "Please help me.", "مبتدئ"),
            ("thank", "شكرا", "Thank you very much.", "مبتدئ")
        ]
    },
    3: {
        "morning": [
            ("happy", "سعيد", "I am happy today.", "مبتدئ"),
            ("sad", "حزين", "She feels sad.", "مبتدئ"),
            ("angry", "غاضب", "He is angry.", "مبتدئ"),
            ("tired", "متعب", "I am tired.", "مبتدئ")
        ],
        "noon": [
            ("teacher", "معلم", "The teacher explains.", "مبتدئ"),
            ("student", "طالب", "The student studies.", "مبتدئ"),
            ("school", "مدرسة", "I go to school.", "مبتدئ"),
            ("class", "فصل", "The class is big.", "مبتدئ")
        ],
        "afternoon": [
            ("write", "يكتب", "Write your name.", "مبتدئ"),
            ("read", "يقرأ", "Read the book.", "مبتدئ"),
            ("speak", "يتحدث", "Speak English.", "مبتدئ"),
            ("listen", "يستمع", "Listen to music.", "مبتدئ")
        ],
        "night": [
            ("morning", "صباح", "Good morning!", "مبتدئ"),
            ("afternoon", "بعد الظهر", "Good afternoon.", "مبتدئ"),
            ("evening", "مساء", "Good evening.", "مبتدئ"),
            ("night", "ليل", "Good night.", "مبتدئ")
        ]
    },
    4: {
        "morning": [
            ("pen", "قلم", "I write with a pen.", "مبتدئ"),
            ("pencil", "قلم رصاص", "Draw with a pencil.", "مبتدئ"),
            ("paper", "ورق", "A piece of paper.", "مبتدئ"),
            ("desk", "مكتب", "The teacher's desk.", "مبتدئ")
        ],
        "noon": [
            ("dog", "كلب", "The dog barks.", "مبتدئ"),
            ("cat", "قطة", "The cat sleeps.", "مبتدئ"),
            ("bird", "طائر", "The bird flies.", "مبتدئ"),
            ("fish", "سمكة", "Fish swim.", "مبتدئ")
        ],
        "afternoon": [
            ("apple", "تفاح", "An apple a day.", "مبتدئ"),
            ("banana", "موز", "Yellow banana.", "مبتدئ"),
            ("orange", "برتقال", "Orange juice.", "مبتدئ"),
            ("grape", "عنب", "Sweet grapes.", "مبتدئ")
        ],
        "night": [
            ("milk", "حليب", "Drink milk.", "مبتدئ"),
            ("bread", "خبز", "Fresh bread.", "مبتدئ"),
            ("cheese", "جبن", "Cheese sandwich.", "مبتدئ"),
            ("egg", "بيضة", "Fried egg.", "مبتدئ")
        ]
    },
    5: {
        "morning": [
            ("day", "يوم", "Today is a nice day.", "مبتدئ"),
            ("week", "أسبوع", "A week has 7 days.", "مبتدئ"),
            ("month", "شهر", "This month is January.", "مبتدئ"),
            ("year", "سنة", "Happy new year.", "مبتدئ")
        ],
        "noon": [
            ("sun", "شمس", "The sun is bright.", "مبتدئ"),
            ("moon", "قمر", "The moon at night.", "مبتدئ"),
            ("star", "نجم", "Twinkling stars.", "مبتدئ"),
            ("sky", "سماء", "Blue sky.", "مبتدئ")
        ],
        "afternoon": [
            ("up", "فوق", "Look up.", "مبتدئ"),
            ("down", "تحت", "Sit down.", "مبتدئ"),
            ("left", "يسار", "Turn left.", "مبتدئ"),
            ("right", "يمين", "Turn right.", "مبتدئ")
        ],
        "night": [
            ("open", "يفتح", "Open the window.", "مبتدئ"),
            ("close", "يغلق", "Close the door.", "مبتدئ"),
            ("enter", "يدخل", "Enter the room.", "مبتدئ"),
            ("exit", "يخرج", "Exit the building.", "مبتدئ")
        ]
    },
    6: {
        "morning": [
            ("man", "رجل", "A tall man.", "مبتدئ"),
            ("woman", "امرأة", "A woman with a bag.", "مبتدئ"),
            ("boy", "ولد", "The boy plays.", "مبتدئ"),
            ("girl", "بنت", "The girl sings.", "مبتدئ")
        ],
        "noon": [
            ("friend", "صديق", "Best friend.", "مبتدئ"),
            ("family", "عائلة", "My family is large.", "مبتدئ"),
            ("baby", "طفل", "The baby cries.", "مبتدئ"),
            ("people", "ناس", "Many people.", "مبتدئ")
        ],
        "afternoon": [
            ("work", "عمل", "I work hard.", "مبتدئ"),
            ("play", "يلعب", "Children play.", "مبتدئ"),
            ("study", "يدرس", "Study for exam.", "مبتدئ"),
            ("rest", "يستريح", "Rest after work.", "مبتدئ")
        ],
        "night": [
            ("city", "مدينة", "Big city.", "مبتدئ"),
            ("town", "بلدة", "Small town.", "مبتدئ"),
            ("village", "قرية", "Quiet village.", "مبتدئ"),
            ("country", "ريف", "Live in the country.", "مبتدئ")
        ]
    },
    7: {
        "morning": [
            ("ask", "يسأل", "Ask a question.", "مبتدئ"),
            ("answer", "يجيب", "Answer the phone.", "مبتدئ"),
            ("give", "يعطي", "Give me the book.", "مبتدئ"),
            ("take", "يأخذ", "Take a seat.", "مبتدئ")
        ],
        "noon": [
            ("help", "يساعد", "Help me, please.", "مبتدئ"),
            ("find", "يجد", "Find your keys.", "مبتدئ"),
            ("lose", "يفقد", "Don't lose hope.", "مبتدئ"),
            ("need", "يحتاج", "I need water.", "مبتدئ")
        ],
        "afternoon": [
            ("love", "حب", "I love you.", "مبتدئ"),
            ("like", "يعجبني", "I like pizza.", "مبتدئ"),
            ("hate", "يكره", "I hate spiders.", "مبتدئ"),
            ("want", "يريد", "I want to travel.", "مبتدئ")
        ],
        "night": [
            ("come", "يأتي", "Come here.", "مبتدئ"),
            ("go", "يذهب", "Go away.", "مبتدئ"),
            ("arrive", "يصل", "Arrive at station.", "مبتدئ"),
            ("leave", "يغادر", "Leave the room.", "مبتدئ")
        ]
    },
    8: {
        "morning": [
            ("begin", "يبدأ", "Let's begin.", "مبتدئ"),
            ("start", "يبدأ", "Start the car.", "مبتدئ"),
            ("finish", "ينهي", "Finish your work.", "مبتدئ"),
            ("stop", "يتوقف", "Stop here.", "مبتدئ")
        ],
        "noon": [
            ("buy", "يشتري", "Buy some milk.", "مبتدئ"),
            ("sell", "يبيع", "Sell your car.", "مبتدئ"),
            ("pay", "يدفع", "Pay the bill.", "مبتدئ"),
            ("cost", "يكلف", "How much does it cost?", "مبتدئ")
        ],
        "afternoon": [
            ("cheap", "رخيص", "Cheap price.", "مبتدئ"),
            ("expensive", "غالي", "Expensive car.", "مبتدئ"),
            ("free", "مجاني", "Free admission.", "مبتدئ"),
            ("price", "سعر", "The price is high.", "مبتدئ")
        ],
        "night": [
            ("time", "وقت", "What time is it?", "مبتدئ"),
            ("hour", "ساعة", "One hour later.", "مبتدئ"),
            ("minute", "دقيقة", "Wait a minute.", "مبتدئ"),
            ("second", "ثانية", "Just a second.", "مبتدئ")
        ]
    },
    9: {
        "morning": [
            ("today", "اليوم", "Today is Monday.", "مبتدئ"),
            ("tomorrow", "غداً", "See you tomorrow.", "مبتدئ"),
            ("yesterday", "أمس", "Yesterday was Sunday.", "مبتدئ"),
            ("now", "الآن", "Do it now.", "مبتدئ")
        ],
        "noon": [
            ("always", "دائماً", "Always be kind.", "مبتدئ"),
            ("usually", "عادةً", "I usually wake up early.", "مبتدئ"),
            ("sometimes", "أحياناً", "Sometimes it rains.", "مبتدئ"),
            ("never", "أبداً", "I never smoke.", "مبتدئ")
        ],
        "afternoon": [
            ("here", "هنا", "Come here.", "مبتدئ"),
            ("there", "هناك", "Put it there.", "مبتدئ"),
            ("everywhere", "في كل مكان", "I looked everywhere.", "مبتدئ"),
            ("somewhere", "في مكان ما", "It's somewhere here.", "مبتدئ")
        ],
        "night": [
            ("fast", "سريع", "Fast car.", "مبتدئ"),
            ("slow", "بطيء", "Slow down.", "مبتدئ"),
            ("quick", "سريع", "Quick response.", "مبتدئ"),
            ("early", "مبكر", "Wake up early.", "مبتدئ")
        ]
    },
    10: {
        "morning": [
            ("new", "جديد", "New phone.", "مبتدئ"),
            ("old", "قديم", "Old house.", "مبتدئ"),
            ("young", "شاب", "Young people.", "مبتدئ"),
            ("modern", "حديث", "Modern design.", "مبتدئ")
        ],
        "noon": [
            ("easy", "سهل", "Easy test.", "مبتدئ"),
            ("difficult", "صعب", "Difficult exam.", "مبتدئ"),
            ("hard", "صعب", "Hard work.", "مبتدئ"),
            ("simple", "بسيط", "Simple answer.", "مبتدئ")
        ],
        "afternoon": [
            ("clean", "نظيف", "Clean room.", "مبتدئ"),
            ("dirty", "قذر", "Dirty clothes.", "مبتدئ"),
            ("empty", "فارغ", "Empty box.", "مبتدئ"),
            ("full", "ممتلئ", "Full glass.", "مبتدئ")
        ],
        "night": [
            ("light", "خفيف/ضوء", "Light weight.", "مبتدئ"),
            ("heavy", "ثقيل", "Heavy bag.", "مبتدئ"),
            ("dark", "مظلم", "Dark night.", "مبتدئ"),
            ("bright", "مشرق", "Bright sun.", "مبتدئ")
        ]
    },
    11: {
        "morning": [
            ("ability", "قدرة", "He has the ability to sing.", "متوسط"),
            ("absence", "غياب", "His absence was noticed.", "متوسط"),
            ("absolute", "مطلق", "Absolute power.", "متوسط"),
            ("absorb", "يمتص", "The sponge absorbs water.", "متوسط")
        ],
        "noon": [
            ("academic", "أكاديمي", "Academic year.", "متوسط"),
            ("accept", "يقبل", "Accept the offer.", "متوسط"),
            ("access", "وصول", "Access to information.", "متوسط"),
            ("accident", "حادث", "Car accident.", "متوسط")
        ],
        "afternoon": [
            ("achieve", "يحقق", "Achieve your goals.", "متوسط"),
            ("act", "يتصرف", "Act quickly.", "متوسط"),
            ("active", "نشط", "Active lifestyle.", "متوسط"),
            ("actual", "فعلي", "Actual facts.", "متوسط")
        ],
        "night": [
            ("adapt", "يتكيف", "Adapt to changes.", "متوسط"),
            ("add", "يضيف", "Add some salt.", "متوسط"),
            ("adjust", "يعدل", "Adjust the volume.", "متوسط"),
            ("admire", "يعجب", "I admire your work.", "متوسط")
        ]
    },
    12: {
        "morning": [
            ("admit", "يعترف", "Admit your mistake.", "متوسط"),
            ("adopt", "يتبنى", "Adopt a child.", "متوسط"),
            ("adult", "بالغ", "Adult education.", "متوسط"),
            ("advance", "يتقدم", "Advance in career.", "متوسط")
        ],
        "noon": [
            ("advantage", "ميزة", "Take advantage.", "متوسط"),
            ("advice", "نصيحة", "Good advice.", "متوسط"),
            ("affair", "شأن", "Personal affair.", "متوسط"),
            ("affect", "يؤثر", "Affect the result.", "متوسط")
        ],
        "afternoon": [
            ("afford", "يستطيع شراء", "I can't afford it.", "متوسط"),
            ("afraid", "خائف", "Afraid of dogs.", "متوسط"),
            ("against", "ضد", "Fight against.", "متوسط"),
            ("age", "عمر", "At your age.", "متوسط")
        ],
        "night": [
            ("agency", "وكالة", "Travel agency.", "متوسط"),
            ("agent", "وكيل", "Secret agent.", "متوسط"),
            ("agree", "يوافق", "I agree with you.", "متوسط"),
            ("ahead", "قدماً", "Go ahead.", "متوسط")
        ]
    },
    13: {
        "morning": [
            ("aid", "مساعدة", "First aid.", "متوسط"),
            ("aim", "هدف", "Aim high.", "متوسط"),
            ("air", "هواء", "Fresh air.", "متوسط"),
            ("allow", "يسمح", "Allow entry.", "متوسط")
        ],
        "noon": [
            ("almost", "تقريباً", "Almost done.", "متوسط"),
            ("alone", "وحيد", "Live alone.", "متوسط"),
            ("along", "بطول", "Walk along.", "متوسط"),
            ("already", "بالفعل", "Already finished.", "متوسط")
        ],
        "afternoon": [
            ("alright", "حسناً", "Alright, let's go.", "متوسط"),
            ("although", "مع أن", "Although it's raining.", "متوسط"),
            ("always", "دائماً", "Always ready.", "متوسط"),
            ("among", "بين", "Among friends.", "متوسط")
        ],
        "night": [
            ("amount", "كمية", "Large amount.", "متوسط"),
            ("ancient", "قديم", "Ancient history.", "متوسط"),
            ("anger", "غضب", "Control your anger.", "متوسط"),
            ("angle", "زاوية", "Right angle.", "متوسط")
        ]
    },
    14: {
        "morning": [
            ("announce", "يعلن", "Announce the news.", "متوسط"),
            ("annoy", "يزعج", "Don't annoy me.", "متوسط"),
            ("annual", "سنوي", "Annual meeting.", "متوسط"),
            ("another", "آخر", "Another chance.", "متوسط")
        ],
        "noon": [
            ("answer", "إجابة", "Correct answer.", "متوسط"),
            ("anticipate", "يتوقع", "Anticipate results.", "متوسط"),
            ("anxiety", "قلق", "Feel anxiety.", "متوسط"),
            ("anyway", "على أي حال", "Anyway, let's continue.", "متوسط")
        ],
        "afternoon": [
            ("apart", "منفصل", "Apart from that.", "متوسط"),
            ("apologize", "يعتذر", "Apologize for being late.", "متوسط"),
            ("apparent", "واضح", "Apparent reason.", "متوسط"),
            ("appeal", "يستأنف/يجذب", "Appeal to the court.", "متوسط")
        ],
        "night": [
            ("appear", "يظهر", "Appear suddenly.", "متوسط"),
            ("apply", "يتقدم/يطبق", "Apply for a job.", "متوسط"),
            ("approach", "يقترب", "Approach the problem.", "متوسط"),
            ("appropriate", "مناسب", "Appropriate time.", "متوسط")
        ]
    },
    15: {
        "morning": [
            ("approve", "يوافق", "Approve the plan.", "متوسط"),
            ("area", "منطقة", "Residential area.", "متوسط"),
            ("argue", "يتجادل", "Argue about politics.", "متوسط"),
            ("arrange", "يرتب", "Arrange the books.", "متوسط")
        ],
        "noon": [
            ("arrest", "يعتقل", "Arrest the thief.", "متوسط"),
            ("arrival", "وصول", "Arrival time.", "متوسط"),
            ("article", "مقال", "Read an article.", "متوسط"),
            ("ashamed", "خجول", "Feel ashamed.", "متوسط")
        ],
        "afternoon": [
            ("aside", "جانباً", "Step aside.", "متوسط"),
            ("ask", "يسأل", "Ask a question.", "متوسط"),
            ("asleep", "نائم", "Fall asleep.", "متوسط"),
            ("aspect", "جانب", "Consider every aspect.", "متوسط")
        ],
        "night": [
            ("assemble", "يجمع", "Assemble the team.", "متوسط"),
            ("assess", "يقيم", "Assess the situation.", "متوسط"),
            ("assign", "يعين", "Assign a task.", "متوسط"),
            ("assist", "يساعد", "Assist the teacher.", "متوسط")
        ]
    },
    16: {
        "morning": [
            ("assume", "يفترض", "Assume it's true.", "متوسط"),
            ("assure", "يؤكد", "Assure safety.", "متوسط"),
            ("atmosphere", "جو", "Friendly atmosphere.", "متوسط"),
            ("attach", "يرفق", "Attach a file.", "متوسط")
        ],
        "noon": [
            ("attack", "يهاجم", "Attack the enemy.", "متوسط"),
            ("attempt", "يحاول", "Attempt to win.", "متوسط"),
            ("attend", "يحضر", "Attend the meeting.", "متوسط"),
            ("attention", "انتباه", "Pay attention.", "متوسط")
        ],
        "afternoon": [
            ("attitude", "موقف", "Positive attitude.", "متوسط"),
            ("attract", "يجذب", "Attract tourists.", "متوسط"),
            ("audience", "جمهور", "Large audience.", "متوسط"),
            ("author", "مؤلف", "Book author.", "متوسط")
        ],
        "night": [
            ("authority", "سلطة", "Local authority.", "متوسط"),
            ("automatic", "تلقائي", "Automatic door.", "متوسط"),
            ("available", "متاح", "Available now.", "متوسط"),
            ("average", "متوسط", "Average score.", "متوسط")
        ]
    },
    17: {
        "morning": [
            ("avoid", "يتجنب", "Avoid trouble.", "متوسط"),
            ("award", "جائزة", "Win an award.", "متوسط"),
            ("aware", "مدرك", "Be aware.", "متوسط"),
            ("awful", "فظيع", "Awful weather.", "متوسط")
        ],
        "noon": [
            ("back", "ظهر/يعود", "Come back.", "متوسط"),
            ("background", "خلفية", "Educational background.", "متوسط"),
            ("balance", "توازن", "Work-life balance.", "متوسط"),
            ("ban", "يحظر", "Ban smoking.", "متوسط")
        ],
        "afternoon": [
            ("band", "فرقة", "Rock band.", "متوسط"),
            ("bar", "شريط/حانة", "Coffee bar.", "متوسط"),
            ("barely", "بالكاد", "Barely enough.", "متوسط"),
            ("battle", "معركة", "Battle field.", "متوسط")
        ],
        "night": [
            ("bear", "يتحمل", "Bear the pain.", "متوسط"),
            ("beat", "يضرب/يهزم", "Beat the record.", "متوسط"),
            ("beauty", "جمال", "Natural beauty.", "متوسط"),
            ("because", "لأن", "Because of you.", "متوسط")
        ]
    },
    18: {
        "morning": [
            ("become", "يصبح", "Become a doctor.", "متوسط"),
            ("before", "قبل", "Before the war.", "متوسط"),
            ("begin", "يبدأ", "Begin now.", "متوسط"),
            ("behave", "يتصرف", "Behave yourself.", "متوسط")
        ],
        "noon": [
            ("behind", "خلف", "Behind the door.", "متوسط"),
            ("believe", "يؤمن", "Believe in yourself.", "متوسط"),
            ("belong", "ينتمي", "Belong to a group.", "متوسط"),
            ("below", "أسفل", "Below zero.", "متوسط")
        ],
        "afternoon": [
            ("beneath", "تحت", "Beneath the surface.", "متوسط"),
            ("benefit", "فائدة", "Health benefits.", "متوسط"),
            ("beside", "بجانب", "Beside the river.", "متوسط"),
            ("bet", "يراهن", "I bet you can.", "متوسط")
        ],
        "night": [
            ("better", "أفضل", "Better than before.", "متوسط"),
            ("between", "بين", "Between us.", "متوسط"),
            ("beyond", "وراء", "Beyond imagination.", "متوسط"),
            ("bill", "فاتورة", "Pay the bill.", "متوسط")
        ]
    },
    19: {
        "morning": [
            ("billion", "مليار", "Billions of stars.", "متوسط"),
            ("bind", "يربط", "Bind the books.", "متوسط"),
            ("birth", "ولادة", "Birth day.", "متوسط"),
            ("bit", "قطعة صغيرة", "A bit of sugar.", "متوسط")
        ],
        "noon": [
            ("bite", "يعض", "Dog bite.", "متوسط"),
            ("blame", "يلوم", "Blame someone.", "متوسط"),
            ("blank", "فارغ", "Blank page.", "متوسط"),
            ("blind", "أعمى", "Blind man.", "متوسط")
        ],
        "afternoon": [
            ("block", "كتلة/يمنع", "Block the road.", "متوسط"),
            ("blood", "دم", "Blood pressure.", "متوسط"),
            ("blow", "ينفخ", "Blow out the candle.", "متوسط"),
            ("board", "لوح", "Board of directors.", "متوسط")
        ],
        "night": [
            ("boast", "يتفاخر", "Boast about success.", "متوسط"),
            ("boat", "قارب", "Fishing boat.", "متوسط"),
            ("body", "جسم", "Human body.", "متوسط"),
            ("boil", "يغلي", "Boil the water.", "متوسط")
        ]
    },
    20: {
        "morning": [
            ("bold", "جريء", "Bold move.", "متوسط"),
            ("bomb", "قنبلة", "Bomb explosion.", "متوسط"),
            ("bond", "رابطة", "Family bond.", "متوسط"),
            ("bone", "عظمة", "Broken bone.", "متوسط")
        ],
        "noon": [
            ("book", "يحجز", "Book a ticket.", "متوسط"),
            ("border", "حدود", "Border crossing.", "متوسط"),
            ("bother", "يزعج", "Don't bother me.", "متوسط"),
            ("bottom", "قاع", "Bottom of the sea.", "متوسط")
        ],
        "afternoon": [
            ("bound", "ملزم", "Bound by law.", "متوسط"),
            ("bow", "ينحني", "Bow down.", "متوسط"),
            ("brain", "دماغ", "Use your brain.", "متوسط"),
            ("branch", "فرع", "Tree branch.", "متوسط")
        ],
        "night": [
            ("brave", "شجاع", "Brave soldier.", "متوسط"),
            ("break", "يكسر", "Break the glass.", "متوسط"),
            ("breath", "نفس", "Take a breath.", "متوسط"),
            ("breathe", "يتنفس", "Breathe deeply.", "متوسط")
        ]
    },
    21: {
        "morning": [
            ("abandon", "يهجر", "Abandon the project.", "متقدم"),
            ("abstract", "مجرد", "Abstract idea.", "متقدم"),
            ("absurd", "عبثي", "Absurd suggestion.", "متقدم"),
            ("abuse", "يسيء", "Abuse power.", "متقدم")
        ],
        "noon": [
            ("accelerate", "يسرع", "Accelerate the car.", "متقدم"),
            ("accommodate", "يستوعب", "Accommodate guests.", "متقدم"),
            ("accompany", "يرافق", "Accompany me.", "متقدم"),
            ("accomplish", "ينجز", "Accomplish a goal.", "متقدم")
        ],
        "afternoon": [
            ("account", "حساب", "Bank account.", "متقدم"),
            ("accumulate", "يتراكم", "Dust accumulates.", "متقدم"),
            ("accuse", "يتهم", "Accuse of theft.", "متقدم"),
            ("achieve", "يحقق", "Achieve success.", "متقدم")
        ],
        "night": [
            ("acknowledge", "يعترف", "Acknowledge mistake.", "متقدم"),
            ("acquire", "يكتسب", "Acquire knowledge.", "متقدم"),
            ("adapt", "يتكيف", "Adapt to environment.", "متقدم"),
            ("address", "يعالج/عنوان", "Address the issue.", "متقدم")
        ]
    },
    22: {
        "morning": [
            ("adequate", "كاف", "Adequate supply.", "متقدم"),
            ("adjust", "يعدل", "Adjust settings.", "متقدم"),
            ("administer", "يدير", "Administer medicine.", "متقدم"),
            ("admire", "يعجب", "Admire the view.", "متقدم")
        ],
        "noon": [
            ("admit", "يعترف", "Admit guilt.", "متقدم"),
            ("adopt", "يتبنى", "Adopt a method.", "متقدم"),
            ("advance", "يتقدم", "Advance in career.", "متقدم"),
            ("adverse", "سلبي", "Adverse effects.", "متقدم")
        ],
        "afternoon": [
            ("advocate", "يدافع", "Advocate for rights.", "متقدم"),
            ("affect", "يؤثر", "Affect the outcome.", "متقدم"),
            ("aggregate", "إجمالي", "Aggregate data.", "متقدم"),
            ("allocate", "يخصص", "Allocate resources.", "متقدم")
        ],
        "night": [
            ("anticipate", "يتوقع", "Anticipate needs.", "متقدم"),
            ("apparent", "واضح", "Apparent reason.", "متقدم"),
            ("appeal", "يستأنف", "Appeal the decision.", "متقدم"),
            ("apply", "يطبق", "Apply the theory.", "متقدم")
        ]
    },
    23: {
        "morning": [
            ("approach", "يقترب", "Approach the problem.", "متقدم"),
            ("appropriate", "مناسب", "Appropriate response.", "متقدم"),
            ("approve", "يوافق", "Approve the plan.", "متقدم"),
            ("arise", "ينشأ", "Problems arise.", "متقدم")
        ],
        "noon": [
            ("aspect", "جانب", "Various aspects.", "متقدم"),
            ("assemble", "يجمع", "Assemble the team.", "متقدم"),
            ("assess", "يقيم", "Assess the damage.", "متقدم"),
            ("assign", "يعين", "Assign tasks.", "متقدم")
        ],
        "afternoon": [
            ("assist", "يساعد", "Assist in research.", "متقدم"),
            ("assume", "يفترض", "Assume responsibility.", "متقدم"),
            ("assure", "يؤكد", "Assure quality.", "متقدم"),
            ("attach", "يرفق", "Attach documents.", "متقدم")
        ],
        "night": [
            ("attain", "يحقق", "Attain success.", "متقدم"),
            ("attempt", "يحاول", "Attempt to escape.", "متقدم"),
            ("attend", "يحضر", "Attend conference.", "متقدم"),
            ("attribute", "ينسب", "Attribute to luck.", "متقدم")
        ]
    },
    24: {
        "morning": [
            ("beneficial", "مفيد", "Beneficial advice.", "متقدم"),
            ("challenge", "تحدي", "Face the challenge.", "متقدم"),
            ("characteristic", "صفة", "Main characteristic.", "متقدم"),
            ("circumstance", "ظرف", "Under circumstances.", "متقدم")
        ],
        "noon": [
            ("coherent", "مترابط", "Coherent argument.", "متقدم"),
            ("coincide", "يتزامن", "Events coincide.", "متقدم"),
            ("collapse", "ينهار", "Building collapses.", "متقدم"),
            ("colleague", "زميل", "Work colleague.", "متقدم")
        ],
        "afternoon": [
            ("commence", "يبدأ", "Commence ceremony.", "متقدم"),
            ("commit", "يرتكب", "Commit a crime.", "متقدم"),
            ("commodity", "سلعة", "Commodity prices.", "متقدم"),
            ("compensate", "يعوض", "Compensate for loss.", "متقدم")
        ],
        "night": [
            ("compile", "يجمع", "Compile data.", "متقدم"),
            ("comply", "يمتثل", "Comply with rules.", "متقدم"),
            ("compose", "يؤلف", "Compose music.", "متقدم"),
            ("comprehend", "يستوعب", "Comprehend the text.", "متقدم")
        ]
    },
    25: {
        "morning": [
            ("comprise", "يتكون من", "Comprise many parts.", "متقدم"),
            ("compromise", "حل وسط", "Reach a compromise.", "متقدم"),
            ("conceal", "يخفي", "Conceal the truth.", "متقدم"),
            ("conceive", "يتصور", "Conceive an idea.", "متقدم")
        ],
        "noon": [
            ("concentrate", "يركز", "Concentrate on work.", "متقدم"),
            ("concept", "مفهوم", "Key concept.", "متقدم"),
            ("concern", "يهتم", "Concern about safety.", "متقدم"),
            ("conclude", "يستنتج", "Conclude the meeting.", "متقدم")
        ],
        "afternoon": [
            ("concrete", "ملموس", "Concrete evidence.", "متقدم"),
            ("conduct", "يقود", "Conduct research.", "متقدم"),
            ("confer", "يتشاور", "Confer with experts.", "متقدم"),
            ("confess", "يعترف", "Confess the crime.", "متقدم")
        ],
        "night": [
            ("confine", "يقيد", "Confine in prison.", "متقدم"),
            ("confirm", "يؤكد", "Confirm the news.", "متقدم"),
            ("conflict", "صراع", "Conflict of interest.", "متقدم"),
            ("conform", "يتوافق", "Conform to rules.", "متقدم")
        ]
    },
    26: {
        "morning": [
            ("confront", "يواجه", "Confront the enemy.", "متقدم"),
            ("confuse", "يربك", "Confuse the issue.", "متقدم"),
            ("connect", "يربط", "Connect the wires.", "متقدم"),
            ("consent", "موافقة", "Parental consent.", "متقدم")
        ],
        "noon": [
            ("consequence", "نتيجة", "Face consequences.", "متقدم"),
            ("conserve", "يحافظ", "Conserve energy.", "متقدم"),
            ("consider", "يعتبر", "Consider the options.", "متقدم"),
            ("consist", "يتكون", "Consist of parts.", "متقدم")
        ],
        "afternoon": [
            ("consistent", "متناسق", "Consistent results.", "متقدم"),
            ("consolidate", "يوحد", "Consolidate power.", "متقدم"),
            ("conspicuous", "واضح", "Conspicuous place.", "متقدم"),
            ("constant", "ثابت", "Constant speed.", "متقدم")
        ],
        "night": [
            ("constitute", "يشكل", "Constitute a threat.", "متقدم"),
            ("constrain", "يقيد", "Constrained by law.", "متقدم"),
            ("construct", "يبني", "Construct a building.", "متقدم"),
            ("consult", "يستشير", "Consult a doctor.", "متقدم")
        ]
    },
    27: {
        "morning": [
            ("consume", "يستهلك", "Consume food.", "متقدم"),
            ("contact", "يتصل", "Contact me later.", "متقدم"),
            ("contemporary", "معاصر", "Contemporary art.", "متقدم"),
            ("contend", "ينافس", "Contend for title.", "متقدم")
        ],
        "noon": [
            ("content", "محتوى", "Table of contents.", "متقدم"),
            ("contest", "مسابقة", "Win the contest.", "متقدم"),
            ("context", "سياق", "In this context.", "متقدم"),
            ("contract", "عقد", "Sign a contract.", "متقدم")
        ],
        "afternoon": [
            ("contradict", "يناقض", "Contradict yourself.", "متقدم"),
            ("contrary", "عكس", "Contrary to belief.", "متقدم"),
            ("contrast", "تباين", "In contrast to.", "متقدم"),
            ("contribute", "يساهم", "Contribute to society.", "متقدم")
        ],
        "night": [
            ("controversy", "جدل", "Cause controversy.", "متقدم"),
            ("convenient", "ملائم", "Convenient time.", "متقدم"),
            ("convention", "اتفاقية", "International convention.", "متقدم"),
            ("converse", "يتحدث", "Converse with friends.", "متقدم")
        ]
    },
    28: {
        "morning": [
            ("convert", "يحول", "Convert currency.", "متقدم"),
            ("convey", "ينقل", "Convey a message.", "متقدم"),
            ("convict", "يدين", "Convict the criminal.", "متقدم"),
            ("convince", "يقنع", "Convince the jury.", "متقدم")
        ],
        "noon": [
            ("cooperate", "يتعاون", "Cooperate with team.", "متقدم"),
            ("coordinate", "ينسق", "Coordinate efforts.", "متقدم"),
            ("cope", "يتأقلم", "Cope with stress.", "متقدم"),
            ("core", "جوهر", "Core values.", "متقدم")
        ],
        "afternoon": [
            ("corporate", "شركة", "Corporate identity.", "متقدم"),
            ("correspond", "يتوافق", "Correspond with facts.", "متقدم"),
            ("counsel", "يستشير", "Seek counsel.", "متقدم"),
            ("counter", "يعارض", "Counter the argument.", "متقدم")
        ],
        "night": [
            ("courtesy", "لباقة", "Courtesy and respect.", "متقدم"),
            ("craft", "حرفة", "Art and craft.", "متقدم"),
            ("crash", "يتحطم", "Car crash.", "متقدم"),
            ("create", "يخلق", "Create new ideas.", "متقدم")
        ]
    },
    29: {
        "morning": [
            ("credible", "موثوق", "Credible source.", "متقدم"),
            ("crime", "جريمة", "Crime rate.", "متقدم"),
            ("crisis", "أزمة", "Economic crisis.", "متقدم"),
            ("criteria", "معايير", "Selection criteria.", "متقدم")
        ],
        "noon": [
            ("critic", "ناقد", "Film critic.", "متقدم"),
            ("crucial", "حاسم", "Crucial moment.", "متقدم"),
            ("crude", "خام", "Crude oil.", "متقدم"),
            ("cultivate", "يزرع", "Cultivate the land.", "متقدم")
        ],
        "afternoon": [
            ("curious", "فضولي", "Curious mind.", "متقدم"),
            ("currency", "عملة", "Foreign currency.", "متقدم"),
            ("current", "حالي", "Current situation.", "متقدم"),
            ("curriculum", "منهج", "School curriculum.", "متقدم")
        ],
        "night": [
            ("custom", "عادة", "Local customs.", "متقدم"),
            ("damage", "ضرر", "Cause damage.", "متقدم"),
            ("debate", "مناظرة", "Political debate.", "متقدم"),
            ("decade", "عقد", "For decades.", "متقدم")
        ]
    },
    30: {
        "morning": [
            ("decay", "تحلل", "Tooth decay.", "متقدم"),
            ("deceive", "يخدع", "Deceive the public.", "متقدم"),
            ("decent", "لائق", "Decent living.", "متقدم"),
            ("decide", "يقرر", "Decide quickly.", "متقدم")
        ],
        "noon": [
            ("declare", "يعلن", "Declare independence.", "متقدم"),
            ("decline", "ينخفض", "Decline in value.", "متقدم"),
            ("decrease", "يقلل", "Decrease speed.", "متقدم"),
            ("dedicate", "يكرس", "Dedicate your life.", "متقدم")
        ],
        "afternoon": [
            ("defeat", "هزيمة", "Accept defeat.", "متقدم"),
            ("defend", "يدافع", "Defend the country.", "متقدم"),
            ("deficiency", "نقص", "Vitamin deficiency.", "متقدم"),
            ("define", "يعرف", "Define the term.", "متقدم")
        ],
        "night": [
            ("definite", "محدد", "Definite answer.", "متقدم"),
            ("delay", "تأخير", "Delay the flight.", "متقدم"),
            ("delegate", "مندوب", "Delegate authority.", "متقدم"),
            ("deliberate", "متعمد", "Deliberate act.", "متقدم")
        ]
    }
}

# تحويل إلى الهيكل المطلوب (قاموس vocab)
vocab = {}
for day in range(1, 31):
    vocab[day] = {}
    for session in ["morning", "noon", "afternoon", "night"]:
        words_list = words_db.get(day, {}).get(session, [])
        vocab[day][session] = [{"eng": w[0], "ar": w[1], "example": w[2], "level": w[3]} for w in words_list]

# ================== متغيرات الحالة ==================
user_sessions = {}
user_quiz_state = {}
user_polls = {}
user_streak = {}

# ================== دوال مساعدة ==================
def get_user_day(user_id):
    c.execute("SELECT current_day FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row[0] if row else 1

def update_user_day(user_id, day):
    c.execute("UPDATE users SET current_day=? WHERE user_id=?", (day, user_id))
    conn.commit()

def get_user_progress_count(user_id):
    c.execute("SELECT COUNT(*) FROM progress WHERE user_id=? AND completed=1", (user_id,))
    return c.fetchone()[0]

def get_completed_days(user_id):
    """ترجع قائمة الأيام التي أكمل المستخدم جميع جلساتها الأربعة"""
    c.execute("SELECT day, COUNT(*) FROM progress WHERE user_id=? AND completed=1 GROUP BY day HAVING COUNT(*)>=4", (user_id,))
    rows = c.fetchall()
    return [row[0] for row in rows]

def can_access_day(user_id, day):
    if day == 1:
        return True
    c.execute("SELECT COUNT(*) FROM progress WHERE user_id=? AND day=? AND completed=1", (user_id, day-1))
    if c.fetchone()[0] < 4:
        return False
    c.execute("SELECT completed_at FROM progress WHERE user_id=? AND day=? AND completed=1 ORDER BY completed_at DESC LIMIT 1", (user_id, day-1))
    row = c.fetchone()
    if row:
        last = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        if datetime.now() - last < timedelta(hours=24):
            return False
    return True

def update_streak(user_id):
    today = datetime.now().date()
    if user_id not in user_streak:
        user_streak[user_id] = {"current": 0, "longest": 0}
    c.execute("SELECT completed_at FROM progress WHERE user_id=? AND completed=1 ORDER BY completed_at DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    if row:
        last = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').date()
        if last == today - timedelta(days=1):
            user_streak[user_id]["current"] += 1
        elif last < today - timedelta(days=1):
            user_streak[user_id]["current"] = 1
        user_streak[user_id]["longest"] = max(user_streak[user_id]["longest"], user_streak[user_id]["current"])
    return user_streak[user_id]

def get_time_until_next_day(user_id, day):
    """حساب الوقت المتبقي لفتح اليوم التالي"""
    c.execute("SELECT completed_at FROM progress WHERE user_id=? AND day=? AND completed=1 ORDER BY completed_at ASC", (user_id, day))
    rows = c.fetchall()
    if len(rows) < 4:
        return None
    # أقل وقت هو وقت أول جلسة في اليوم
    first_time = datetime.strptime(rows[0][0], '%Y-%m-%d %H:%M:%S')
    target_time = first_time + timedelta(hours=24)
    now = datetime.now()
    if now >= target_time:
        return 0
    delta = target_time - now
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    return f"{hours} ساعة و {minutes} دقيقة"

def get_next_session(current_session):
    """ترجع الجلسة التالية"""
    sessions = ["morning", "noon", "afternoon", "night"]
    try:
        idx = sessions.index(current_session)
        if idx < len(sessions) - 1:
            return sessions[idx + 1]
    except ValueError:
        pass
    return None

def create_main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("📚 ابدأ اليوم"), KeyboardButton("📘 قواعد أساسية"))
    markup.add(KeyboardButton("⭐ مفضلتي"), KeyboardButton("📊 إحصائياتي"))
    markup.add(KeyboardButton("🎓 شهادتي"))
    return markup

def create_styled_button(text, callback_data, style="default"):
    try:
        return InlineKeyboardButton(text, callback_data=callback_data, style=style)
    except TypeError:
        return InlineKeyboardButton(text, callback_data=callback_data)

def create_grammar_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        create_styled_button("🔤 الحروف المتحركة", "grammar_vowels", "primary"),
        create_styled_button("🔠 الحروف الساكنة", "grammar_consonants", "primary")
    )
    markup.add(
        create_styled_button("📖 أدوات التعريف", "grammar_articles", "primary"),
        create_styled_button("👤 الضمائر الشخصية", "grammar_pronouns", "primary")
    )
    markup.add(
        create_styled_button("⏰ الأزمنة البسيطة", "grammar_tenses", "success"),
        create_styled_button("➕ جمع الأسماء", "grammar_plurals", "success")
    )
    markup.add(
        create_styled_button("📍 حروف الجر", "grammar_prepositions", "success"),
        create_styled_button("❓ أدوات الاستفهام", "grammar_questions", "success")
    )
    markup.add(create_styled_button("🔙 العودة", "back_main", "danger"))
    return markup

def create_session_keyboard(day):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        create_styled_button("🌅 صباح", f"session_{day}_morning", "primary"),
        create_styled_button("☀️ ظهر", f"session_{day}_noon", "success")
    )
    markup.add(
        create_styled_button("🌇 عصر", f"session_{day}_afternoon", "primary"),
        create_styled_button("🌙 ليل", f"session_{day}_night", "success")
    )
    return markup

def create_days_keyboard_with_progress(user_id):
    """إنشاء لوحة أيام مع ✅ بجانب الأيام المكتملة"""
    completed_days = get_completed_days(user_id)
    markup = InlineKeyboardMarkup(row_width=5)
    buttons = []
    for day in range(1, 31):
        text = f"يوم {day}"
        if day in completed_days:
            text += " ✅"
        buttons.append(InlineKeyboardButton(text, callback_data=f"day_{day}"))
    for i in range(0, 30, 5):
        markup.add(*buttons[i:i+5])
    return markup

# ================== دوال إنشاء الصور ==================
def generate_daily_result_image(user_id, day, score, total):
    if not HAS_PIL:
        return None
    try:
        img = Image.new('RGB', (600, 400), (255, 255, 255))
        d = ImageDraw.Draw(img)
        try:
            font_large = ImageFont.truetype("arial.ttf", 36)
            font_medium = ImageFont.truetype("arial.ttf", 28)
            font_small = ImageFont.truetype("arial.ttf", 20)
        except:
            font_large = ImageFont.load_default()
            font_medium = font_large
            font_small = font_large
        d.rectangle([(20,20),(580,380)], outline=(0,100,200), width=3)
        d.text((300, 60), f"📅 نتيجة اليوم {day}", fill=(0,100,200), font=font_large, anchor="mm")
        percent = (score/total)*100
        color = (0,200,0) if percent >= 70 else (200,0,0)
        d.text((300, 140), f"{score}/{total}  ({percent:.1f}%)", fill=color, font=font_large, anchor="mm")
        if percent >= 90:
            estimation = "🌟 ممتاز! مستوى متقدم"
            message = "استمر بهذا الأداء الرائع!"
        elif percent >= 75:
            estimation = "👍 جيد جداً"
            message = "أنت في الطريق الصحيح!"
        elif percent >= 60:
            estimation = "📚 جيد"
            message = "راجع الكلمات التي أخطأت فيها"
        else:
            estimation = "⚠️ يحتاج تحسين"
            message = "لا تستسلم، كرر المحاولة!"
        d.text((300, 200), estimation, fill=(100,100,100), font=font_medium, anchor="mm")
        d.text((300, 260), message, fill=(0,0,0), font=font_small, anchor="mm")
        d.text((300, 320), datetime.now().strftime('%Y-%m-%d'), fill=(150,150,150), font=font_small, anchor="mm")
        filename = f"daily_{user_id}_{day}.png"
        img.save(filename)
        return filename
    except:
        return None

def generate_certificate_image(user_id, name):
    if not HAS_PIL:
        return None
    try:
        img = Image.new('RGB', (800, 600), (255, 255, 255))
        d = ImageDraw.Draw(img)
        try:
            font_title = ImageFont.truetype("arial.ttf", 40)
            font_name = ImageFont.truetype("arial.ttf", 50)
            font_text = ImageFont.truetype("arial.ttf", 30)
        except:
            font_title = ImageFont.load_default()
            font_name = font_title
            font_text = font_title
        d.rectangle([(50,50),(750,550)], outline=(255,215,0), width=5)
        d.text((400,120), "شهادة إتمام", fill=(255,215,0), font=font_title, anchor="mm")
        d.text((400,200), "يتشرف الطالب", fill=(0,0,0), font=font_text, anchor="mm")
        d.text((400,260), name, fill=(0,0,150), font=font_name, anchor="mm")
        d.text((400,340), "بإكمال برنامج تحضير التوفل", fill=(0,0,0), font=font_text, anchor="mm")
        d.text((400,400), "30 يوم - 120 جلسة", fill=(0,100,0), font=font_text, anchor="mm")
        d.text((400,480), f"{datetime.now().strftime('%Y-%m-%d')}", fill=(100,100,100), font=font_text, anchor="mm")
        filename = f"cert_{user_id}.png"
        img.save(filename)
        return filename
    except:
        return None

# ================== دوال الاستفتاءات ==================
def get_random_wrong_meaning(correct_meaning, exclude_word=None, level=None):
    """الحصول على معنى خاطئ عشوائي من كلمات أخرى"""
    all_meanings = []
    for d in range(1, 31):
        for s in ["morning","noon","afternoon","night"]:
            for w in vocab[d][s]:
                if w['ar'] != correct_meaning and (not level or w['level'] == level):
                    all_meanings.append(w['ar'])
    if not all_meanings:
        return "معنى آخر"
    return random.choice(all_meanings)

def send_word_poll(chat_id, word_data, poll_type, poll_number, total_polls):
    """إرسال استفتاء عن الكلمة مع خيارات حقيقية"""
    eng = word_data['eng']
    ar = word_data['ar']
    example = word_data['example']
    level = word_data['level']
    
    if poll_type == "meaning":
        question = f"({poll_number}/{total_polls}) ما معنى كلمة '{eng}'؟"
        options = [ar]
        for _ in range(3):
            wrong = get_random_wrong_meaning(ar, level=level)
            options.append(wrong)
        random.shuffle(options)
        correct_index = options.index(ar)
        explanation = f"✅ {ar}\n📝 مثال: {example}"
        return bot.send_poll(chat_id, question, options, type='quiz', correct_option_id=correct_index,
                             explanation=explanation, open_period=30, is_anonymous=False)
    
    elif poll_type == "example":
        question = f"({poll_number}/{total_polls}) أي جملة تستخدم '{eng}' بشكل صحيح؟"
        options = [example]
        wrong_examples = []
        for d in range(1, 31):
            for s in ["morning","noon","afternoon","night"]:
                for w in vocab[d][s]:
                    if w['example'] != example:
                        wrong_examples.append(w['example'])
        random.shuffle(wrong_examples)
        options.extend(wrong_examples[:3])
        random.shuffle(options)
        correct_index = options.index(example)
        explanation = f"✅ الجملة الصحيحة: {example}"
        return bot.send_poll(chat_id, question, options, type='quiz', correct_option_id=correct_index,
                             explanation=explanation, open_period=30, is_anonymous=False)
    
    elif poll_type == "true_false":
        if random.choice([True, False]):
            statement = f"كلمة '{eng}' تعني '{ar}'"
            correct = True
        else:
            wrong_ar = get_random_wrong_meaning(ar, level=level)
            statement = f"كلمة '{eng}' تعني '{wrong_ar}'"
            correct = False
        question = f"({poll_number}/{total_polls}) هل العبارة التالية صحيحة؟\n\n{statement}"
        options = ["✅ صحيح", "❌ خطأ"]
        correct_index = 0 if correct else 1
        explanation = f"المعنى الصحيح: {ar}\nمثال: {example}"
        return bot.send_poll(chat_id, question, options, type='quiz', correct_option_id=correct_index,
                             explanation=explanation, open_period=30, is_anonymous=False)

def start_quiz(chat_id, user_id, day, session):
    """بدء اختبار بـ 8 أسئلة"""
    words = vocab[day][session][:]
    if day > 1:
        review_words = []
        for d in range(max(1, day-3), day):
            for s in ["morning","noon","afternoon","night"]:
                review_words.extend(vocab[d][s][:2])
        if review_words:
            random.shuffle(review_words)
            words.extend(review_words)
    random.shuffle(words)
    quiz_words = []
    if len(words) >= 8:
        quiz_words = words[:8]
    else:
        while len(quiz_words) < 8:
            quiz_words.extend(words)
        quiz_words = quiz_words[:8]
        random.shuffle(quiz_words)
    
    question_types = [random.choice(["meaning","example","true_false"]) for _ in range(8)]
    
    user_quiz_state[user_id] = {
        "day": day,
        "session": session,
        "words": quiz_words,
        "types": question_types,
        "current": 0,
        "score": 0,
        "total": 8,
        "poll_ids": []
    }
    
    bot.send_message(chat_id, f"🎯 بدء الاختبار: 8 أسئلة")
    send_next_quiz_poll(chat_id, user_id)

def send_next_quiz_poll(chat_id, user_id):
    state = user_quiz_state.get(user_id)
    if not state or state["current"] >= state["total"]:
        finish_quiz(chat_id, user_id)
        return
    idx = state["current"]
    word = state["words"][idx]
    qtype = state["types"][idx]
    poll_num = idx + 1
    total = state["total"]
    poll_msg = send_word_poll(chat_id, word, qtype, poll_num, total)
    if poll_msg:
        state["poll_ids"].append(poll_msg.poll.id)
        user_polls[poll_msg.poll.id] = {
            "user_id": user_id,
            "chat_id": chat_id,
            "q_index": idx,
            "word": word,
            "correct_option_id": poll_msg.poll.correct_option_id
        }

def finish_quiz(chat_id, user_id):
    state = user_quiz_state.get(user_id)
    if not state:
        return
    
    score = state.get("score", 0)
    total = state["total"]
    day = state["day"]
    session = state["session"]
    
    # حفظ النتيجة
    today = datetime.now().date()
    c.execute("INSERT OR REPLACE INTO daily_results (user_id, day, score, total, date) VALUES (?,?,?,?,?)",
              (user_id, day, score, total, today))
    conn.commit()
    
    # إرسال صورة النتيجة
    img_file = generate_daily_result_image(user_id, day, score, total)
    if img_file:
        with open(img_file, 'rb') as f:
            bot.send_photo(chat_id, f)
        os.remove(img_file)
    else:
        percent = (score/total)*100
        stars = "⭐" * int(percent/20) + "✨" * (5 - int(percent/20))
        msg = f"📊 **نتيجة الاختبار**\n"
        msg += f"📅 اليوم {day}\n"
        msg += f"✅ الإجابات الصحيحة: {score}\n"
        msg += f"❌ الإجابات الخاطئة: {total - score}\n"
        msg += f"📈 النسبة: {percent:.1f}%\n"
        msg += f"{stars}\n"
        if percent >= 80:
            msg += "🌟 **ممتاز!**"
        elif percent >= 60:
            msg += "👍 **جيد جداً**"
        else:
            msg += "💪 **حاول مرة أخرى**"
        bot.send_message(chat_id, msg, parse_mode="Markdown")
    
    # تسجيل الجلسة كمكتملة في progress
    c.execute("INSERT OR REPLACE INTO progress (user_id, day, session, completed, completed_at) VALUES (?,?,?,1,?)",
              (user_id, day, session, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    
    # التحقق من الجلسات المتبقية في اليوم
    c.execute("SELECT session FROM progress WHERE user_id=? AND day=? AND completed=1", (user_id, day))
    completed_sessions = [row[0] for row in c.fetchall()]
    all_sessions = ["morning", "noon", "afternoon", "night"]
    remaining = [s for s in all_sessions if s not in completed_sessions]
    
    if remaining:
        # لا يزال هناك جلسات متبقية، نعرض زر للجلسة التالية
        next_sesh = remaining[0]
        session_names = {"morning": "🌅 الصباح", "noon": "☀️ الظهر", "afternoon": "🌇 العصر", "night": "🌙 الليل"}
        next_name = session_names.get(next_sesh, next_sesh)
        markup = InlineKeyboardMarkup().add(
            create_styled_button(f"⏩ الانتقال إلى {next_name}", f"session_{day}_{next_sesh}", "primary")
        )
        bot.send_message(chat_id, f"🎉 تم إكمال جلسة {session_names.get(session, session)}!\nتابع إلى الجلسة التالية:", reply_markup=markup)
    else:
        # تم إكمال كل جلسات اليوم
        bot.send_message(chat_id, f"🎉 أكملت اليوم {day} بنجاح!")
        # تحديث اليوم الحالي للمستخدم
        if day == get_user_day(user_id):
            update_user_day(user_id, day+1)
        
        # حساب الوقت المتبقي لليوم التالي
        time_left = get_time_until_next_day(user_id, day)
        if time_left == 0:
            # يمكن فتح اليوم التالي مباشرة
            markup = InlineKeyboardMarkup().add(
                create_styled_button("🚀 ابدأ اليوم التالي", f"day_{day+1}", "success")
            )
            bot.send_message(chat_id, "يمكنك البدء باليوم التالي الآن!", reply_markup=markup)
        elif time_left:
            markup = InlineKeyboardMarkup().add(
                create_styled_button(f"⏳ انتظر {time_left}", "wait", "danger")
            )
            bot.send_message(chat_id, f"⏰ يجب الانتظار {time_left} لبدء اليوم التالي.", reply_markup=markup)
    
    # تنظيف
    if user_id in user_quiz_state:
        del user_quiz_state[user_id]

# ================== معالج الاستفتاءات ==================
@bot.poll_answer_handler()
def handle_poll_answer(pollAnswer):
    poll_id = pollAnswer.poll_id
    user_id = pollAnswer.user.id
    selected = pollAnswer.option_ids
    
    if poll_id not in user_polls:
        return
    
    data = user_polls[poll_id]
    if data["user_id"] != user_id:
        return
    
    state = user_quiz_state.get(user_id)
    if not state or data["q_index"] != state["current"]:
        return
    
    correct_id = data.get("correct_option_id")
    if correct_id is not None and selected and selected[0] == correct_id:
        state["score"] += 1
    
    state["current"] += 1
    send_next_quiz_poll(data["chat_id"], user_id)
    
    if poll_id in user_polls:
        del user_polls[poll_id]

# ================== الأوامر الرئيسية ==================
@bot.message_handler(commands=['start', 'menu'])
def cmd_start(message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    c.execute("INSERT OR IGNORE INTO users (user_id, username, name, join_date) VALUES (?,?,?,?)",
              (user_id, message.from_user.username, name, datetime.now().date()))
    conn.commit()
    
    welcome = f"مرحباً {name}! 👋\nاختر من القائمة:"
    bot.send_message(message.chat.id, welcome, reply_markup=create_main_keyboard())
    
    # عرض قائمة الأيام فوراً بعد القائمة الرئيسية (اختياري)
    days_markup = create_days_keyboard_with_progress(user_id)
    bot.send_message(message.chat.id, "📅 اختر اليوم الذي تريد البدء به:", reply_markup=days_markup)

@bot.message_handler(func=lambda m: m.text == "📚 ابدأ اليوم")
def start_today(message):
    user_id = message.from_user.id
    days_markup = create_days_keyboard_with_progress(user_id)
    bot.send_message(message.chat.id, "📅 اختر اليوم الذي تريد البدء به:", reply_markup=days_markup)

@bot.message_handler(func=lambda m: m.text == "📘 قواعد أساسية")
def grammar_menu(message):
    bot.send_message(message.chat.id, "اختر موضوع القواعد:", reply_markup=create_grammar_keyboard())

@bot.message_handler(func=lambda m: m.text == "⭐ مفضلتي")
def show_favorites(message):
    user_id = message.from_user.id
    c.execute("SELECT word FROM favorites WHERE user_id=? ORDER BY word", (user_id,))
    rows = c.fetchall()
    if not rows:
        bot.send_message(message.chat.id, "لا توجد كلمات مفضلة بعد.\nأثناء عرض الكلمات اضغط على ⭐ لإضافتها.")
        return
    
    markup = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for (word,) in rows:
        buttons.append(InlineKeyboardButton(word, callback_data=f"fav_{word}"))
    for i in range(0, len(buttons), 3):
        markup.add(*buttons[i:i+3])
    bot.send_message(message.chat.id, "⭐ كلماتك المفضلة:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 إحصائياتي")
def show_stats(message):
    user_id = message.from_user.id
    progress = get_user_progress_count(user_id)
    day = get_user_day(user_id)
    streak = update_streak(user_id)
    c.execute("SELECT COUNT(*) FROM favorites WHERE user_id=?", (user_id,))
    favs = c.fetchone()[0]
    c.execute("SELECT AVG(score*1.0/total) FROM daily_results WHERE user_id=?", (user_id,))
    avg = c.fetchone()[0]
    avg = round(avg*100, 2) if avg else 0
    msg = f"📊 إحصائياتك:\n✅ الجلسات المنجزة: {progress}/120\n📅 اليوم الحالي: {day}\n🔥 التتابع: {streak['current']} يوم\n🏆 أطول تتابع: {streak['longest']}\n⭐ المفضلة: {favs}\n📈 متوسط النتائج: {avg}%"
    bot.send_message(message.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "🎓 شهادتي")
def request_certificate(message):
    user_id = message.from_user.id
    progress = get_user_progress_count(user_id)
    if progress < 120:
        bot.send_message(message.chat.id, f"لم تكمل البرنامج بعد! تحتاج {120-progress} جلسة أخرى.")
        return
    bot.send_message(message.chat.id, "ما اسمك الذي تريد كتابته على الشهادة؟")
    bot.register_next_step_handler(message, process_certificate_name)

def process_certificate_name(message):
    user_id = message.from_user.id
    name = message.text
    cert_file = generate_certificate_image(user_id, name)
    if cert_file:
        with open(cert_file, 'rb') as f:
            bot.send_photo(message.chat.id, f, caption="🎉 تهانينا! شهادة إتمام البرنامج")
        os.remove(cert_file)
    else:
        bot.send_message(message.chat.id, f"🎉 تهانينا {name}! أكملت البرنامج بنجاح.")

# ================== معالج الكولباك ==================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    cid = call.message.chat.id
    user_id = call.from_user.id
    data = call.data

    if data.startswith("day_"):
        day = int(data.split("_")[1])
        if not can_access_day(user_id, day):
            # حساب الوقت المتبقي وعرضه للمستخدم
            if day == 1:
                # اليوم الأول دائماً متاح، لكن هذا لن يحدث لأن can_access_day true
                pass
            else:
                # نحتاج لمعرفة متى يمكن فتح هذا اليوم
                # نجلب وقت أول جلسة لليوم السابق
                c.execute("SELECT completed_at FROM progress WHERE user_id=? AND day=? AND completed=1 ORDER BY completed_at ASC", (user_id, day-1))
                rows = c.fetchall()
                if len(rows) >= 4:
                    first_time = datetime.strptime(rows[0][0], '%Y-%m-%d %H:%M:%S')
                    target = first_time + timedelta(hours=24)
                    now = datetime.now()
                    if now < target:
                        delta = target - now
                        hours = delta.seconds // 3600
                        minutes = (delta.seconds % 3600) // 60
                        bot.answer_callback_query(call.id, f"⏳ يتبقى {hours} ساعة و {minutes} دقيقة لفتح هذا اليوم.", show_alert=True)
                    else:
                        bot.answer_callback_query(call.id, "يمكنك فتح اليوم الآن! حاول مرة أخرى.", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, "❌ يجب إكمال اليوم السابق أولاً.", show_alert=True)
            return
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            create_styled_button("🌅 صباح", f"session_{day}_morning", "primary"),
            create_styled_button("☀️ ظهر", f"session_{day}_noon", "success"),
            create_styled_button("🌇 عصر", f"session_{day}_afternoon", "primary"),
            create_styled_button("🌙 ليل", f"session_{day}_night", "success")
        )
        markup.add(create_styled_button("🔙 العودة للأيام", "back_to_days", "danger"))
        bot.edit_message_text(f"**يوم {day} 📅**\nاختر وقت الجلسة:", cid, call.message.message_id, reply_markup=markup, parse_mode='Markdown')
    
    elif data == "back_to_days":
        markup = create_days_keyboard_with_progress(user_id)
        bot.edit_message_text("📅 اختر اليوم:", cid, call.message.message_id, reply_markup=markup)
    
    elif data.startswith("session_"):
        _, day, session = data.split("_")
        day = int(day)
        session_map = {"morning": "🌅 صباح", "noon": "☀️ ظهر", "afternoon": "🌇 عصر", "night": "🌙 ليل"}
        session_name = session_map.get(session, session)
        
        words = vocab[day][session][:]
        # إضافة مراجعة
        if day > 1:
            review = []
            for d in range(max(1, day-3), day):
                for s in ["morning","noon","afternoon","night"]:
                    review.extend(vocab[d][s][:2])
            if review:
                review = random.sample(review, min(4, len(review)))
                for w in review:
                    w_copy = w.copy()
                    w_copy['eng'] = "🔄 " + w_copy['eng']
                    words.append(w_copy)
        
        user_sessions[user_id] = words
        
        bot.edit_message_text(f"**{session_name} - يوم {day}**\nعرض الكلمات:", cid, call.message.message_id, parse_mode="Markdown")
        
        for idx, w in enumerate(words):
            display_eng = w['eng'].replace("🔄 ", "")
            msg = f"**{idx+1}. {display_eng}**\n📝 {w['ar']}\n💬 {w['example']}\n📊 المستوى: {w['level']}"
            fav_btn = InlineKeyboardMarkup().add(InlineKeyboardButton("⭐ أضف للمفضلة", callback_data=f"addfav_{idx}"))
            bot.send_message(cid, msg, parse_mode="Markdown", reply_markup=fav_btn)
            try:
                tts = gTTS(display_eng, lang='en')
                fn = f"word_{time.time()}.mp3"
                tts.save(fn)
                with open(fn, 'rb') as f:
                    bot.send_voice(cid, f)
                os.remove(fn)
            except:
                pass
        
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            create_styled_button("✅ إنهاء الجلسة", f"complete_{day}_{session}", "success"),
            create_styled_button("🎯 اختبار (8 أسئلة)", f"quiz_{day}_{session}", "primary")
        )
        bot.send_message(cid, "ماذا تريد أن تفعل الآن؟", reply_markup=markup)
    
    elif data.startswith("addfav_"):
        idx = int(data.split("_")[1])
        words = user_sessions.get(user_id, [])
        if 0 <= idx < len(words):
            w = words[idx]
            clean_eng = w['eng'].replace("🔄 ", "")
            c.execute("INSERT OR IGNORE INTO favorites (user_id, word, meaning, example, level) VALUES (?,?,?,?,?)",
                      (user_id, clean_eng, w['ar'], w['example'], w['level']))
            conn.commit()
            bot.answer_callback_query(call.id, f"تمت إضافة {clean_eng} إلى المفضلة ⭐")
        else:
            bot.answer_callback_query(call.id, "حدث خطأ")
    
    elif data.startswith("complete_"):
        _, day, session = data.split("_")
        day = int(day)
        c.execute("INSERT OR REPLACE INTO progress (user_id, day, session, completed, completed_at) VALUES (?,?,?,1,?)",
                  (user_id, day, session, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        bot.answer_callback_query(call.id, "✅ تم حفظ التقدم")
        
        # التحقق من الجلسات المتبقية في اليوم
        c.execute("SELECT session FROM progress WHERE user_id=? AND day=? AND completed=1", (user_id, day))
        completed_sessions = [row[0] for row in c.fetchall()]
        all_sessions = ["morning", "noon", "afternoon", "night"]
        remaining = [s for s in all_sessions if s not in completed_sessions]
        
        if remaining:
            # لا يزال هناك جلسات متبقية، نعرض زر للجلسة التالية
            next_sesh = remaining[0]
            session_names = {"morning": "🌅 الصباح", "noon": "☀️ الظهر", "afternoon": "🌇 العصر", "night": "🌙 الليل"}
            next_name = session_names.get(next_sesh, next_sesh)
            markup = InlineKeyboardMarkup().add(
                create_styled_button(f"⏩ الانتقال إلى {next_name}", f"session_{day}_{next_sesh}", "primary")
            )
            bot.send_message(cid, f"🎉 تم إكمال جلسة {session_names.get(session, session)}!\nتابع إلى الجلسة التالية:", reply_markup=markup)
        else:
            # تم إكمال كل جلسات اليوم
            bot.send_message(cid, f"🎉 أكملت اليوم {day} بنجاح!")
            # تحديث اليوم الحالي للمستخدم
            if day == get_user_day(user_id):
                update_user_day(user_id, day+1)
            
            # حساب الوقت المتبقي لليوم التالي
            time_left = get_time_until_next_day(user_id, day)
            if time_left == 0:
                # يمكن فتح اليوم التالي مباشرة
                markup = InlineKeyboardMarkup().add(
                    create_styled_button("🚀 ابدأ اليوم التالي", f"day_{day+1}", "success")
                )
                bot.send_message(cid, "يمكنك البدء باليوم التالي الآن!", reply_markup=markup)
            elif time_left:
                markup = InlineKeyboardMarkup().add(
                    create_styled_button(f"⏳ انتظر {time_left}", "wait", "danger")
                )
                bot.send_message(cid, f"⏰ يجب الانتظار {time_left} لبدء اليوم التالي.", reply_markup=markup)
    
    elif data.startswith("quiz_"):
        _, day, session = data.split("_")
        day = int(day)
        start_quiz(cid, user_id, day, session)
        bot.edit_message_text("بدء الاختبار...", cid, call.message.message_id)
    
    elif data.startswith("fav_"):
        word = data[4:]
        c.execute("SELECT meaning, example, level FROM favorites WHERE user_id=? AND word=?", (user_id, word))
        row = c.fetchone()
        if row:
            meaning, example, level = row
            msg = f"**{word}**\n📝 {meaning}\n💬 {example}\n📊 المستوى: {level}"
            bot.send_message(cid, msg, parse_mode="Markdown")
            try:
                tts = gTTS(word, lang='en')
                fn = f"fav_{time.time()}.mp3"
                tts.save(fn)
                with open(fn, 'rb') as f:
                    bot.send_voice(cid, f)
                os.remove(fn)
            except:
                pass
        else:
            bot.answer_callback_query(call.id, "الكلمة غير موجودة")
    
    elif data.startswith("grammar_"):
        topic = data[8:]
        texts = {
            "vowels": "🔤 **الحروف المتحركة** (Vowels): A, E, I, O, U (وأحياناً Y).\nتظهر في كل كلمة تقريباً.",
            "consonants": "🔠 **الحروف الساكنة** (Consonants) هي باقي الحروف الأبجدية.",
            "articles": "📖 **أدوات التعريف**:\n- a : قبل الحرف الساكن (a book)\n- an : قبل الحرف المتحرك (an apple)\n- the : للمعرفة",
            "pronouns": "👤 **الضمائر الشخصية**:\nI, You, He, She, It, We, They\nو ضمائر المفعول: me, you, him, her, it, us, them",
            "tenses": "⏰ **الأزمنة البسيطة**:\n- Past: I walked\n- Present: I walk\n- Future: I will walk",
            "plurals": "➕ **جمع الأسماء**:\nعادة بإضافة s (cat→cats)\nإذا انتهى بـ s, ss, sh, ch, x, o نضيف es (box→boxes)\nاستثناءات: child→children, man→men",
            "prepositions": "📍 **حروف الجر**: in, on, at, for, to, from, with, about",
            "questions": "❓ **أدوات الاستفهام**: What, Where, When, Why, How, Who"
        }
        content = texts.get(topic, "معلومات عن القواعد")
        bot.send_message(cid, f"<blockquote>{content}</blockquote>", parse_mode="HTML")
    
    elif data == "back_main":
        bot.edit_message_text("القائمة الرئيسية:", cid, call.message.message_id, reply_markup=create_grammar_keyboard())
    
    elif data.startswith("wait"):
        bot.answer_callback_query(call.id, "الرجاء الانتظار حتى انتهاء الوقت المتبقي", show_alert=False)

# ================== تشغيل البوت ==================
if __name__ == "__main__":
    print("✅ البوت يعمل مع 480 كلمة حقيقية ونتائج مصورة وتنقل تلقائي بين الجلسات...")
    bot.infinity_polling()
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    server.serve_forever()

threading.Thread(target=run_web).start()
bot.infinity_polling()
