const TelegramBot = require('node-telegram-bot-api');
const ytdl = require('@distube/ytdl-core');

const token = process.env.BOT_TOKEN;
const bot = new TelegramBot(token, { polling: true });

let brokenHearts = 0;
let lastMessages = {};

console.log("💔 ALQEADH Bot is running...");

// رسالة البداية
bot.onText(/\/start/, (msg) => {
    bot.sendMessage(msg.chat.id,
        "💔 مرحباً بك في بوت تحميل ALQEADH 💔\n\nأرسل رابط يوتيوب لجلب المعلومات."
    );
});

// عند استقبال رابط
bot.on('message', async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text;

    if (!text || !ytdl.validateURL(text)) return;

    try {
        const info = await ytdl.getInfo(text);
        const title = info.videoDetails.title;
        const views = info.videoDetails.viewCount;
        const duration = info.videoDetails.lengthSeconds;
        const thumbnail = info.videoDetails.thumbnails.pop().url;

        const minutes = Math.floor(duration / 60);
        const seconds = duration % 60;

        // حذف الرسالة السابقة إن وجدت
        if (lastMessages[chatId]) {
            try {
                await bot.deleteMessage(chatId, lastMessages[chatId]);
            } catch {}
        }

        const sent = await bot.sendPhoto(chatId, thumbnail, {
            caption:
                `🎬 ${title}\n\n` +
                `⏱ ${minutes}:${seconds < 10 ? "0"+seconds : seconds}\n` +
                `👁 ${views} مشاهدة\n\n` +
                `💔 عدد القلوب المكسورة: ${brokenHearts}`,
            reply_markup: {
                inline_keyboard: [
                    [{ text: "📹 تحميل فيديو", callback_data: "video_" + text }],
                    [{ text: "🎵 تحميل صوت", callback_data: "audio_" + text }]
                ]
            }
        });

        lastMessages[chatId] = sent.message_id;

    } catch (err) {
        bot.sendMessage(chatId, "❌ حدث خطأ أثناء جلب المعلومات.");
    }
});

// عند الضغط على زر
bot.on("callback_query", async (query) => {
    const chatId = query.message.chat.id;
    const messageId = query.message.message_id;
    const data = query.data;

    brokenHearts++;

    await bot.deleteMessage(chatId, messageId);

    const url = data.split("_")[1];

    if (data.startsWith("video_")) {
        bot.sendMessage(chatId, "⬇ جاري تحميل الفيديو... 💔");

        const stream = ytdl(url, { quality: '18' });

        bot.sendVideo(chatId, stream);
    }

    if (data.startsWith("audio_")) {
        bot.sendMessage(chatId, "⬇ جاري تحميل الصوت... 💔");

        const stream = ytdl(url, { filter: 'audioonly' });

        bot.sendAudio(chatId, stream);
    }

    bot.answerCallbackQuery(query.id);
});
