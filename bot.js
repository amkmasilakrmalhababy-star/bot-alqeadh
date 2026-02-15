const TelegramBot = require('node-telegram-bot-api');
const ytdl = require('@distube/ytdl-core');

const token = process.env.BOT_TOKEN;
const bot = new TelegramBot(token, { polling: true });

let brokenHearts = 0;
let lastMessages = {};

console.log("💔 ALQEADH Bot is running...");

// رسالة البداية
bot.onText(/\/start/, (msg) => {
    bot.sendMessage(
        msg.chat.id,
        "💔 مرحباً بك في بوت تحميل ALQEADH 💔\n\nأرسل رابط يوتيوب لجلب المعلومات."
    );
});

// استقبال أي رسالة
bot.on("message", async (msg) => {
    const chatId = msg.chat.id;
    const text = msg.text;

    if (!text) return;
    if (!ytdl.validateURL(text)) return;

    try {
        const info = await ytdl.getInfo(text);
        const details = info.videoDetails;

        const title = details.title;
        const views = details.viewCount;
        const duration = parseInt(details.lengthSeconds);
        const thumbnail = details.thumbnails.pop().url;

        const minutes = Math.floor(duration / 60);
        const seconds = duration % 60;

        // حذف الرسالة السابقة
        if (lastMessages[chatId]) {
            try {
                await bot.deleteMessage(chatId, lastMessages[chatId]);
            } catch {}
        }

        const sent = await bot.sendPhoto(chatId, thumbnail, {
            caption:
                `🎬 ${title}\n\n` +
                `⏱ ${minutes}:${seconds < 10 ? "0" + seconds : seconds}\n` +
                `👁 ${views} مشاهدة\n\n` +
                `💔 عدد القلوب المكسورة: ${brokenHearts}`,
            reply_markup: {
                inline_keyboard: [
                    [{ text: "📹 تحميل فيديو", callback_data: "video|" + text }],
                    [{ text: "🎵 تحميل صوت", callback_data: "audio|" + text }]
                ]
            }
        });

        lastMessages[chatId] = sent.message_id;

    } catch (err) {
        console.log(err);
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

    const [type, url] = data.split("|");

    try {

        if (type === "video") {
            await bot.sendMessage(chatId, "⬇ جاري تحميل الفيديو... 💔");

            const info = await ytdl.getInfo(url);

            const format = ytdl.chooseFormat(info.formats, {
                quality: "highest",
                filter: "audioandvideo"
            });

            const stream = ytdl(url, { format });

            await bot.sendVideo(chatId, stream);
        }

        if (type === "audio") {
            await bot.sendMessage(chatId, "⬇ جاري تحميل الصوت... 💔");

            const stream = ytdl(url, {
                quality: "highestaudio",
                filter: "audioonly"
            });

            await bot.sendAudio(chatId, stream);
        }

    } catch (error) {
        console.log(error);
        bot.sendMessage(chatId, "❌ فشل التحميل، جرب فيديو آخر.");
    }

    bot.answerCallbackQuery(query.id);
});
