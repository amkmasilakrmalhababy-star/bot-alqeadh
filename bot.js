const TelegramBot = require('node-telegram-bot-api');
const ytdl = require('ytdl-core');
const fs = require('fs');

const token = process.env.BOT_TOKEN;
const bot = new TelegramBot(token, { polling: true });

let brokenHearts = 0;

bot.onText(/\/start/, (msg) => {
    bot.sendMessage(msg.chat.id,
        "💔 مرحباً بك في بوت تحميل ALQEADH 💔\n\nأرسل رابط يوتيوب ليتم جلب المعلومات.",
    );
});

bot.on("message", async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text;

    if (!text) return;

    if (ytdl.validateURL(text)) {
        try {
            const info = await ytdl.getInfo(text);
            const title = info.videoDetails.title;
            const thumbnail = info.videoDetails.thumbnails.pop().url;

            brokenHearts++;

            await bot.sendPhoto(chatId, thumbnail, {
                caption:
                `💔 ALQEADH 💔\n\n🎬 ${title}\n\nاختر نوع التحميل:`,
                reply_markup: {
                    inline_keyboard: [
                        [
                            { text: "🎵 تحميل صوت", callback_data: "audio|" + text }
                        ],
                        [
                            { text: "🎥 تحميل فيديو", callback_data: "video|" + text }
                        ]
                    ]
                }
            });

        } catch (err) {
            bot.sendMessage(chatId, "حدث خطأ أثناء جلب المعلومات.");
        }
    }
});

bot.on("callback_query", async (query) => {
    const chatId = query.message.chat.id;
    const data = query.data.split("|");

    if (data[0] === "audio") {
        const url = data[1];
        const stream = ytdl(url, { filter: 'audioonly' });
        bot.sendAudio(chatId, stream);
    }

    if (data[0] === "video") {
        const url = data[1];
        const stream = ytdl(url, { quality: '18' });
        bot.sendVideo(chatId, stream);
    }

    bot.answerCallbackQuery(query.id);
});

console.log("ALQEADH Bot is running...");
