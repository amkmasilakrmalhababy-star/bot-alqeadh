const TelegramBot = require('node-telegram-bot-api');

const token = process.env.BOT_TOKEN;
const bot = new TelegramBot(token, { polling: true });

let brokenHearts = 0;

bot.onText(/\/start/, (msg) => {
    bot.sendMessage(msg.chat.id, 
        "💔 مرحباً بك في بوت تحميل ALQEADH 💔\n\nاضغط على الزر للحماية أو التحميل.",
        {
            reply_markup: {
                inline_keyboard: [
                    [{ text: "🛡 حماية", callback_data: "protect" }],
                    [{ text: "⬇ تحميل", callback_data: "download" }]
                ]
            }
        }
    );
});

bot.on("callback_query", async (query) => {
    const chatId = query.message.chat.id;
    const messageId = query.message.message_id;

    if (query.data === "protect") {
        brokenHearts++;
        await bot.deleteMessage(chatId, messageId);
        bot.sendMessage(chatId, `🛡 تم تفعيل الحماية بنجاح 💔\nعدد القلوب المكسورة: ${brokenHearts}`);
    }

    if (query.data === "download") {
        brokenHearts++;
        await bot.deleteMessage(chatId, messageId);
        bot.sendMessage(chatId, `⬇ جاري التحميل... 💔\nعدد القلوب المكسورة: ${brokenHearts}`);
    }

    bot.answerCallbackQuery(query.id);
});

console.log("ALQEADH Bot is running...");
