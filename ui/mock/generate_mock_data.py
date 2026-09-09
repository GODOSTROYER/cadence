"""Generate realistic, schema-exact mock data for the Cadence UI static mode.

Writes ``ui/public/data/{eval_summary,failure_modes,golden_merged,decisions,health,intents,escalation}.json``
so the whole UI renders with ``VITE_STATIC=1`` before real results exist. ``scripts/07_export_ui_data.py``
overwrites the result files later; ``intents.json`` and ``escalation.json`` are derived from ``config/``.

Everything is deterministic (``SEED`` from ``cadence.config``). Messages are written in the voice of real
@SpotifyCares customers (several are lifted from ``config/intents.yaml``); replies follow the brand's
"Hey there! ... one concrete step" pattern. Escalation rule flags are produced by actually running the
regexes from ``config/escalation.yaml`` over each message, and every metric in ``eval_summary.json`` is
computed from per-example arrays so confusion rows sum to support and F1 matches the matrix.

Run from the repo root: ``python ui/mock/generate_mock_data.py``
"""

from __future__ import annotations

import argparse
import json
import re
import string
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

from cadence.config import (
    JUDGED_SYSTEMS,
    SEED,
    Paths,
    escalation_config,
    intents_config,
    models_config,
)

OUT_DIR: Path = Paths.UI_PUBLIC_DATA
GENERATED_AT = "2026-09-08T21:14:03Z"
JUDGE_DIMS = ("grounded", "resolves", "tone", "safe", "overall")
FLAG_NAMES = ("hallucinated_link_or_policy", "asks_sensitive_info", "wrong_issue")

# Short aliases keep the example table readable.
PB = "playback_or_app_bug"
DL = "download_or_offline"
LG = "login_or_password"
SEC = "account_hacked_or_security"
BIL = "billing_or_charge"
SUB = "subscription_or_plan"
CON = "content_or_availability"
MD = "metadata_or_artist_issue"
PL = "playlist_or_library"
FR = "feature_request_or_feedback"
NE = "non_english"
OT = "other"

CONFUSABLE: dict[str, list[str]] = {
    PB: [DL, CON, OT],
    DL: [PB, SUB],
    LG: [SEC, OT, SUB],
    SEC: [LG, PL],
    BIL: [SUB, LG],
    SUB: [BIL, FR],
    MD: [CON, FR, PL],
    CON: [PL, MD, PB],
    PL: [CON, PB, SEC],
    FR: [OT, SUB, CON],
    NE: [OT, PB, BIL],
    OT: [FR, PB, NE],
}

RESOLVED_LINK_BY_INTENT: dict[str, str] = {
    PB: "https://support.spotify.com/article/reinstall-spotify/",
    DL: "https://support.spotify.com/article/listen-offline/",
    LG: "https://www.spotify.com/password-reset/",
    SEC: "https://www.spotify.com/account/overview/",
    BIL: "https://support.spotify.com/article/payment-help/",
    SUB: "https://support.spotify.com/article/premium-plans/",
    MD: "https://artists.spotify.com/help",
    CON: "https://support.spotify.com/article/music-not-available/",
    PL: "https://support.spotify.com/article/recover-playlists/",
    FR: "https://community.spotify.com/t5/Ideas/idb-p/ideas",
    NE: "https://support.spotify.com/",
    OT: "https://support.spotify.com/contact-spotify-support/",
}

TRIVIAL_TEMPLATE = (
    "Hey there! We'd like to help. Can you send us a DM with your account's username or email address? "
    "We'll take a closer look backstage"
)


@dataclass
class Spec:
    """One hand-written golden example plus the agent's designed behaviour on it."""

    intent: str
    escalate: bool
    reason: str | None
    sentiment: str
    text: str
    hist: str
    agent_reply: str
    media_only: bool = False
    notes: str = ""
    follow: str | None = None  # "fixed" | "still" | None -> multi-turn thread
    agent_intent: str | None = None
    agent_decision: str | None = None
    agent_reason: str | None = None
    agent_conf: float | None = None
    secondary: str | None = None
    ann_a: dict[str, Any] = field(default_factory=dict)
    ann_b: dict[str, Any] = field(default_factory=dict)


# fmt: off
SPECS: list[Spec] = [
    Spec(PB, False, None, "frustrated",
         "app keeps crashing every time I open it since the update. iPhone 7, iOS 11.1",
         "Hey! Sorry to hear that. Can you try a clean reinstall of the app? Here's how: <url>. Let us know how it goes",
         "Hey there! Sorry about the crashes. A clean reinstall usually clears this after an update, steps here: https://support.spotify.com/article/reinstall-spotify/ Let us know if it keeps happening and we'll dig in /AI",
         follow="still"),
    Spec(PB, False, None, "neutral",
         "web player just stops playing or doesn't even play to begin with. chrome on windows 10",
         "Hi there! Could you try clearing your browser's cache and cookies, then restarting Chrome? If that doesn't help, let us know if you see any error messages",
         "Hey! Let's get that sorted. Try clearing Chrome's cache and cookies, then reload open.spotify.com. Still stuck? Tell us any error message you see and we'll take a closer look /AI"),
    Spec(PB, False, None, "frustrated",
         "can't connect to my Sonos anymore, keeps disconnecting every 2 songs 😤",
         "Hey! Can you make sure both the Spotify and Sonos apps are up to date, then log out of Spotify in the Sonos app and back in? Keep us posted",
         "Hey there! Sorry about the drop-outs. Make sure both apps are up to date, then log out of Spotify inside the Sonos app and back in. Keep us posted on how it goes /AI",
         follow="fixed"),
    Spec(PB, False, None, "frustrated",
         "songs keep skipping halfway through on my Galaxy S8, wifi is fine, restarted twice",
         "Hey! Does this happen with downloaded songs too? Try heading to Settings > Storage > Delete cache and let us know if it helps",
         "Hey! That's not right. In the app head to Settings > Storage > Delete cache, then restart your phone. If songs still skip, let us know whether downloaded tracks do it too /AI"),
    Spec(PB, True, "high_frustration_or_churn", "angry",
         "This is the third time I've asked. The app STILL won't play anything on my Xbox after the update. Fix it or I'm cancelling my premium",
         "We hear you and we're sorry for the trouble. Can you DM us your Xbox model and the app version? We'd like to take a closer look",
         "We hear you, and sorry for the runaround. Can you DM us your Xbox model and the app version you're on? We'd like to pick this up properly /AI",
         notes="repeat contact + explicit churn threat"),
    Spec(PB, False, None, "neutral",
         "Getting error code 17 when trying to open the desktop app on my new laptop. any ideas?",
         "Hey! Error 17 usually means a firewall or antivirus is blocking the app. This should help: <url>. Let us know if it works",
         "Hey! Error 17 usually means a firewall or antivirus is blocking Spotify. Add the app as an exception and try again, full steps: https://support.spotify.com/article/error-codes/ Let us know how you get on /AI"),
    Spec(DL, False, None, "frustrated",
         "all my downloaded albums got removed AGAIN. this is the 4th time this month, 30GB gone",
         "Hey! Sorry about that. Downloads can be removed if you haven't gone online in 30 days or you're using more than 3 devices offline. Can you check that and let us know?",
         "Hey! Sorry about that, it's frustrating. Downloads get removed if the app hasn't gone online in 30 days or you've hit the 3,333-song limit per device. Check both, then re-download, and let us know if it happens again /AI",
         notes="repeated contact; B wanted escalation for churn risk",
         ann_b={"should_escalate": True, "escalation_reason_code": "high_frustration_or_churn"}),
    Spec(DL, False, None, "neutral",
         "offline mode says songs unavailable even though I downloaded them yesterday. going on a flight in 3 hours pls help",
         "Hey! Try toggling Offline Mode off and on under Settings > Playback, and make sure you've opened the app online at least once since downloading. Have a good flight!",
         "Hey! Toggle Offline Mode off and on under Settings > Playback, then check the tracks show a green arrow. If they still say unavailable, re-download over wifi before you board. Safe travels! /AI",
         follow="fixed"),
    Spec(DL, False, None, "neutral",
         "can I move my downloads to the SD card on Android? internal storage is full",
         "Hi! Yes you can. Head to Settings > Other > Storage in the app and choose your SD card. You'll need to download your music again afterwards",
         "Hi! Yes, in the app go to Settings > Storage and pick your SD card. Heads up: you'll need to re-download your music afterwards. More here: https://support.spotify.com/article/storage-settings/ /AI"),
    Spec(DL, False, None, "frustrated",
         "downloads keep saying 'waiting to download' for hours, tried wifi and 4G",
         "Hey! Can you check that Settings > Download using cellular is on if you're on 4G, and that your device has enough free storage? A clean reinstall can also help: <url>",
         "Hey! Check two things: Settings > Music Quality > Download using cellular is on (for 4G), and your phone has free storage left. If they still stall, a clean reinstall clears it: https://support.spotify.com/article/reinstall-spotify/ /AI"),
    Spec(LG, True, "needs_account_lookup", "frustrated",
         "deleted my Facebook without unlinking Spotify first and now I can't log in. 6 years of playlists 😭",
         "Hey! Don't worry, we can help. Can you DM us the email address linked to your Facebook account? We'll take a look backstage",
         "Hey! Don't worry, your playlists aren't gone. Recovering a Facebook-linked account needs a look backstage, can you DM us the email that was on your Facebook profile? /AI"),
    Spec(LG, True, "needs_account_lookup", "neutral",
         "my mum can't remember her password and the email she used no longer exists, what can she do?",
         "Hi! We'd be happy to help. Could you DM us with her username or any email address she might have used? We'll take a look",
         "Hi! We can help with that. Since the reset email can't reach her, we'll need to check the account. Can you DM us her username or any email she may have signed up with? /AI"),
    Spec(LG, True, "needs_account_lookup", "frustrated",
         "password reset email never arrives, checked spam, tried 5 times",
         "Hey! Sorry about that. Can you DM us the email address you're using? We'll check which one is on the account",
         "Hey! Sorry about that. If the reset email isn't landing, the address on the account may differ from the one you're entering. DM us the email you're using and we'll check /AI",
         notes="A thought generic reset steps suffice; adjudicated to escalate (needs lookup)",
         ann_a={"should_escalate": False, "escalation_reason_code": None, "notes": "generic reset steps exist"}),
    Spec(LG, False, None, "neutral",
         "how do I change the email on my account? the settings page just spins",
         "Hey! You can change it at <url> under Edit Profile. If the page keeps loading, try another browser or clearing your cache",
         "Hey! You can update it at spotify.com/account under Edit profile. If the page keeps spinning, try a different browser or an incognito window and it should go through /AI"),
    Spec(LG, False, None, "neutral",
         "I keep getting logged out every few hours on the app, is that normal?",
         "Hey! That's not normal. Try logging out everywhere from <url>, then log back in on your phone. Let us know if it keeps happening",
         "Hey! Being signed out repeatedly can be a sign someone else is using the account. Can you DM us your username so we can check recent activity? /AI",
         agent_intent=SEC, agent_decision="escalate", agent_reason="account_security", agent_conf=0.66),
    Spec(SEC, True, "account_security", "frustrated",
         "spotify is being played on a device I do not own, has there been a security issue?",
         "Hey! Let's get this sorted. Change your password and use 'Sign out everywhere' at <url>. Then DM us your username and we'll take a look",
         "Hey! Let's lock this down. Change your password, then use Sign out everywhere at spotify.com/account. Can you also DM us your username? We'll check the account /AI"),
    Spec(SEC, True, "account_security", "angry",
         "someone changed my email and I'm locked out, my account got hacked",
         "We're sorry to hear that. Please DM us with your username and the original email address, and we'll help you get back in",
         "Sorry to hear that. We'll need to look at this backstage. Please DM us your username and the email address the account used to have, and we'll help you get back in /AI"),
    Spec(SEC, True, "account_security", "frustrated",
         "there's a playlist called 'Reggaeton Mix' in my library that I never made and my Discover Weekly is all in Spanish now. did someone get into my account?",
         "Hey! That sounds like someone else may be using your account. Change your password and sign out everywhere at <url>, then DM us your username",
         "Hey! Discover Weekly reflects what's been played on the account recently. Remove the playlist and hit 'don't like' on the tracks in Discover Weekly, and it'll rebalance next Monday /AI",
         agent_intent=PL, agent_decision="auto_handle", agent_conf=0.74),
    Spec(SEC, True, "account_security", "frustrated",
         "got an email saying my password was changed but I didn't do it. help",
         "Hey! Reset your password right away at <url> and sign out everywhere. Then DM us your username so we can check the account",
         "Hey! Reset your password straight away at spotify.com/password-reset and use Sign out everywhere. Then DM us your username so we can check what happened /AI"),
    Spec(BIL, True, "billing_dispute", "frustrated",
         "why is my credit card getting charged yet I keep getting emails saying I haven't paid",
         "Hey! Sorry for the confusion. Can you DM us your username and the last 4 digits of the card so we can check the payments?",
         "Hey! Sorry for the mixed messages. Payments need a look at the account. Can you DM us your username and the date of the last charge? We'll sort it out /AI"),
    Spec(BIL, True, "billing_dispute", "frustrated",
         "I am not able to pay for my 3 month subscription, tried 3 times",
         "Hey! Sorry about that. Can you DM us your username and which payment method you're using? We'll take a look",
         "Hey! Sorry about that. Could you DM us your username and the payment method you're trying? We'll take a look at what's blocking it /AI"),
    Spec(BIL, True, "billing_dispute", "angry",
         "charged £9.99 twice this month, cancelled in September. want my money back",
         "Hey! We're sorry about that. Please DM us your username so we can check the payments on the account",
         "Hey! Sorry about that. We'll need to check the payments on the account. Please DM us your username and we'll look into the charges /AI"),
    Spec(BIL, True, "billing_dispute", "angry",
         "bought a $30 gift card and the code says already redeemed?? 😡",
         "Hey! Sorry about that. Can you DM us a photo of the back of the card with the code visible? We'll check it out",
         "Hey! Sorry about that. Can you DM us a photo of the back of the gift card with the code visible and where you bought it? We'll check it out /AI"),
    Spec(BIL, True, "billing_dispute", "frustrated",
         "my student discount ended and I got billed full price without warning",
         "Hey! Student discounts last 12 months and need to be renewed. You can re-verify at <url>. If you have questions about the charge, DM us your username",
         "Hey! Sorry for the surprise. Student pricing needs re-verifying every 12 months. Do that at spotify.com/student and we'll refund the difference for this month. DM us your username /AI",
         secondary=SUB),
    Spec(SUB, False, None, "neutral",
         "I'm a student but UNiDAYS doesn't cover my course, can I still get the discount?",
         "Hey! Student discounts are verified through UNiDAYS, so your institution needs to be on their list. You can check eligibility here: <url>",
         "Hey! Student pricing is verified through UNiDAYS, so your institution needs to be on their list, check here: https://support.spotify.com/article/premium-student/ If it isn't listed, UNiDAYS can add schools on request /AI",
         ann_b={"should_escalate": True, "escalation_reason_code": "needs_account_lookup", "notes": "eligibility is per-user"}),
    Spec(SUB, False, None, "neutral",
         "how do I add my sister to the family plan if she lives at another address?",
         "Hey! Premium for Family is for people living at the same address. More info here: <url>",
         "Hey! Premium for Family is for people who live at the same address, so a different address won't verify. Details here: https://support.spotify.com/article/premium-family/ /AI"),
    Spec(SUB, False, None, "positive",
         "is premium still $9.99 a month or did the price go up? thinking about upgrading from free",
         "Hey! Premium is $9.99/month in the US, and you can try it free for 30 days: <url>",
         "Hey! Premium is $9.99 a month in the US and there's a 30-day free trial to start with: https://www.spotify.com/premium/ /AI"),
    Spec(SUB, False, None, "neutral",
         "does the free trial auto renew? don't want to get charged if I forget to cancel",
         "Hey! Yes, the trial rolls into a paid subscription unless you cancel before it ends. You can cancel anytime at <url>",
         "Hey! Yes, the trial rolls into Premium unless you cancel before it ends. You can cancel any time at spotify.com/account and keep listening until the trial's up /AI"),
    Spec(SUB, False, None, "neutral",
         "can I pause my premium for 2 months instead of cancelling? going travelling",
         "Hey! There's no pause option, but you can cancel and resubscribe when you're back. Your playlists and saved music stay put",
         "Hey! There's no pause option, but you can cancel at spotify.com/account and resubscribe when you're back. Your playlists and saved music stay exactly where they are /AI"),
    Spec(CON, False, None, "frustrated",
         "why tf is Garth Brooks not on Spotify",
         "Hey! Artists and labels decide where their music is available. We'd love to have his music too, so keep an eye out!",
         "Hey! Artists and their labels decide where their music is available, and Garth Brooks hasn't licensed his catalogue to us. We'd love to have it too, we'll shout if that changes /AI"),
    Spec(CON, False, None, "frustrated",
         "getting 'this song is not available' for many popular artists on desktop, greyed out everywhere",
         "Hey! Greyed out tracks usually aren't available in your country. If you think it's an error, try logging out and back in and let us know",
         "Hey! Greyed-out tracks are usually not available in your country, or hidden by the 'Show unavailable songs' setting. Check Settings > Display options, then log out and in. Still greyed? Let us know an example /AI"),
    Spec(CON, False, None, "positive",
         "can we have Spotify in Egypt please 🙏",
         "Hey! We're always working to bring Spotify to new places, but we don't have news about Egypt yet. Keep an eye on <url>",
         "Hey! We're always working on bringing Spotify to more countries, but we don't have news about Egypt yet. Keep an eye on spotify.com for launches, we'd love to see you there /AI"),
    Spec(CON, False, None, "frustrated",
         "the new Taylor Swift album shows up but every track is greyed out. I have premium",
         "Hey! Some releases go live at midnight local time, so it may just need a bit longer. Try restarting the app in a few hours",
         "Hey! New releases go live at midnight local time, so it may need a few more hours. In the meantime check the region-lock guide: https://support.spotify.com/article/greyed-out-release-windows/ /AI"),
    Spec(CON, False, None, "neutral",
         "the explicit version of an album is missing, only the clean one is there. any way to get it?",
         "Hey! Some albums are only available as the clean version depending on what the label provides. If you think it's missing in error, let us know the artist and album",
         "Hey! Labels decide which versions they send us, so some albums only arrive as the clean edit. If you think it's an error, tell us the artist and album and we'll flag it /AI"),
    Spec(PL, False, None, "frustrated",
         "why did lots of songs in my playlist stop reproducing?",
         "Hey! Are the songs greyed out? That usually means they're no longer available in your country. If not, try a clean reinstall: <url>",
         "Hey! Are those tracks greyed out or do they skip when you press play? If they skip, try Settings > Storage > Delete cache and restart the app. Let us know which it is /AI",
         notes="ESL phrasing; A read it as a playback bug",
         agent_intent=PB, agent_conf=0.61,
         ann_a={"intent": PB, "notes": "songs won't play = playback"}),
    Spec(PL, False, None, "positive",
         "are you going to release the Your Top Songs of 2017 playlist?",
         "Hey! Your 2017 Wrapped is coming in early December. Keep an eye out!",
         "Hey! Yes, Your Top Songs 2017 arrives with Wrapped in early December. It'll show up in your library and at spotify.com/wrapped 🎶 /AI"),
    Spec(PL, False, None, "frustrated",
         "my entire library disappeared after logging in on my new phone. 2000 songs. please tell me they're recoverable",
         "Hey! Don't panic. Check you're logged in with the same account (Facebook vs email login can create a second account). Let us know if that's the case",
         "Hey! Don't panic, they're almost certainly still there. Check you signed in with the same method as before (Facebook vs email can create a second, empty account). Still missing? DM us your username /AI"),
    Spec(PL, False, None, "neutral",
         "Discover Weekly hasn't updated in 3 weeks, still the same songs from October",
         "Hey! Try unfollowing and refollowing Discover Weekly, then restart the app. It should refresh on Monday",
         "Hey! Try unfollowing Discover Weekly, restarting the app, then following it again from Browse. It'll refresh with the next Monday update /AI"),
    Spec(FR, False, None, "neutral",
         "please introduce beatmatching when crossfade is enabled",
         "Hey! Thanks for the suggestion. We'd recommend posting it in the Ideas section of our Community so others can vote: <url>",
         "Hey! Nice idea. The best place for it is the Ideas board on the Community, where the team reads and others can vote: https://community.spotify.com/t5/Ideas/idb-p/ideas /AI"),
    Spec(FR, False, None, "positive",
         "any chance of a Spotify app for the Nintendo Switch?",
         "Hey! Nothing to share on that right now, but you can add your vote here: <url>",
         "Hey! Nothing to announce on a Switch app right now, but requests like this get counted. Add your vote on the Ideas board: https://community.spotify.com/t5/Ideas/idb-p/ideas /AI"),
    Spec(FR, False, None, "frustrated",
         "the new UI update is awful, why did you move the search bar. bring back the old design",
         "Hey! Sorry to hear you're not a fan. We're always working on the app based on feedback like this, so thanks for letting us know",
         "Hey! Sorry the new layout isn't landing for you. Feedback like this shapes what we change next, so thanks for telling us. The Community Ideas board is the best place to make it count /AI"),
    Spec(FR, False, None, "neutral",
         "please add a sleep timer to the mobile app, I fall asleep to podcasts and wake up 40 episodes later",
         "Hey! Thanks for the idea. Post it on the Community Ideas board so others can vote: <url>",
         "Hey! We've all been there. There's no sleep timer in the app yet, add your voice to the request on the Community Ideas board so it gets counted: https://community.spotify.com/t5/Ideas/idb-p/ideas /AI"),
    Spec(NE, False, None, "neutral",
         "hola no puedo iniciar sesión en mi cuenta",
         "Hi! We're only able to help in English here. For Spanish support, head to <url> or send us a DM and we'll do our best",
         "Hi! We can only help in English on this channel. For support in Spanish, head to https://support.spotify.com/es/ or DM us and we'll do our best /AI"),
    Spec(NE, False, None, "neutral",
         "não consigo ouvir músicas offline",
         "Hi! We can help in English here. For Portuguese, head over to <url> and the team there will take a look",
         "Hi! We can only help in English on this channel. For support in Portuguese, head to https://support.spotify.com/br/ or DM us and we'll do our best /AI"),
    Spec(NE, False, None, "neutral",
         "spotify premium tidak bisa dibayar pakai kartu saya, tolong bantu",
         "Hi! We can help in English here, or you can head to <url> for support in Bahasa Indonesia",
         "Hey! Sorry about that. Card payments need a look at the account. Can you DM us your username and the card type? We'll check what's blocking it /AI",
         agent_intent=BIL, agent_decision="escalate", agent_reason="billing_dispute", agent_conf=0.72),
    Spec(NE, False, None, "neutral",
         "el spotify connect no funciona con mi alexa desde la actualización",
         "Hi! We're only able to help in English here. For Spanish support, head to <url>",
         "Hey! Make sure both the Spotify and Alexa apps are up to date, then unlink and relink Spotify in the Alexa app under Skills. Let us know if Connect still doesn't show up /AI",
         agent_intent=PB, agent_conf=0.79),
    Spec(OT, True, "ambiguous_or_media_only", "neutral",
         "ummm what am I supposed to do? <url>",
         "Hey! We're not able to see the screenshot clearly. Can you tell us what's happening and which device you're using?",
         "Hey! That error usually clears with a quick restart of the app. If it comes back, try a clean reinstall: https://support.spotify.com/article/reinstall-spotify/ /AI",
         media_only=True, agent_intent=PB, agent_decision="auto_handle", agent_conf=0.71),
    Spec(OT, True, "ambiguous_or_media_only", "neutral",
         "<url>",
         "Hey! Can you tell us a bit more about what's going on? We'd like to help",
         "Hey! We can't see what's in the image on our end. Can you tell us a bit more about what's going on and which device you're on? /AI",
         media_only=True, agent_conf=0.55),
    Spec(OT, True, "out_of_scope", "positive",
         "may I pls come to the nyc holiday party?",
         "Ha! We'd love to have you, but it's a team-only affair. Enjoy the holidays!",
         "Ha! We'd love to, but that one's team only. We can still help with anything Spotify-related though, enjoy the holidays 🎶 /AI",
         agent_conf=0.83),
    Spec(OT, False, None, "positive",
         "thank you so much for fixing my account, you guys are the best 💚",
         "You're very welcome! Glad we could help. Enjoy the music!",
         "You're very welcome! Glad it's all sorted. Enjoy the music 💚 /AI",
         agent_conf=0.91),
    Spec(OT, True, "ambiguous_or_media_only", "neutral",
         "this 🙃 <url>",
         "Hey! Can you let us know what's happening? We can't see the image clearly on our end",
         "Hey! Greyed-out tracks usually aren't available in your country yet. If it's a new release, it should unlock at midnight local time /AI",
         media_only=True, agent_intent=CON, agent_decision="auto_handle", agent_conf=0.68),
    Spec(OT, True, "ambiguous_or_media_only", "frustrated",
         "seriously?? <url>",
         "Hey! Sorry about that. Could you tell us what's going on and which device you're on? We'll take a look",
         "Hey! Sorry about that. Can you tell us what you're seeing and which device you're on? We'll take a look /AI",
         media_only=True, agent_intent=PB, agent_decision="escalate", agent_reason="low_confidence", agent_conf=0.52),
    Spec(LG, True, "needs_account_lookup", "frustrated",
         "logged in this morning and all my playlists are gone and it says I'm on Free, I've had premium for years. what happened?",
         "Hey! It sounds like you may have logged into a different account. Try logging out and back in with the email you used to sign up, and DM us your username if it's still off",
         "Hey! Try restoring them at spotify.com/account under Recover playlists, deleted playlists can be brought back for 90 days. Let us know if any are missing after that /AI",
         agent_intent=PL, agent_decision="auto_handle", agent_conf=0.70),
    Spec(SUB, False, None, "neutral",
         "if I upgrade to family plan do I pay the difference or the full £14.99?",
         "Hey! When you switch to Premium for Family you'll be charged the full price on your next billing date, and any remaining time on your current plan carries over",
         "Hey! You pay the full £14.99 from your next billing date, and any remaining days on your current Premium carry over rather than being lost. More here: https://support.spotify.com/article/premium-family/ /AI"),
    Spec(NE, False, None, "neutral",
         "mi discover weekly no se actualiza desde hace 3 semanas 😢",
         "Hi! We can help in English here. For Spanish support, head to <url>",
         "Hey! Try unfollowing Discover Weekly, restarting the app, then following it again from Browse. It refreshes every Monday /AI",
         agent_intent=PL, agent_conf=0.77),
    Spec(PB, False, None, "neutral",
         "Spotify Connect shows my TV but nothing plays when I pick it. LG webOS, app updated",
         "Hey! Try restarting both the TV and your phone, then log out of Spotify on the TV and back in. Let us know if that helps",
         "Hey! Restart both the TV and your phone, then sign out of Spotify on the TV and back in. If Connect still goes quiet, tell us the TV model and we'll take a look /AI"),
    Spec(MD, False, None, "neutral",
         "hey looks like one of our songs was linked to the wrong artist page. Would you be able to help us out?",
         "Hey! Sorry about that. Track credits come from your distributor or label, so ask them to send a correction. Our artist team can help too: <url>",
         "Hey! Sorry about the mix-up. Track credits come from your distributor or label, so ask them to submit a correction and it'll update within a few days. Artist support can help too: https://artists.spotify.com/help /AI"),
    Spec(MD, False, None, "neutral",
         "Drain Sth's song 'Crack the Liar's Smile' is named 'Crack the War's Smile' incorrectly. Just FYI.",
         "Hey! Thanks for flagging that. We've passed it along to the team to take a look",
         "Hey! Thanks for flagging that. We'll pass the title fix to the catalogue team; corrections like this usually land within a week or two /AI"),
    Spec(MD, False, None, "frustrated",
         "the album cover for Hounds of Love is showing a completely different album's artwork on the app",
         "Hey! Thanks for letting us know. Can you send us the album link and a screenshot in a DM so we can check?",
         "Hey! Greyed-out or swapped artwork usually means the album was re-delivered by the label. Try logging out and back in; if it still shows the wrong cover, send us the album link /AI",
         agent_intent=CON, agent_conf=0.64),
    Spec(MD, False, None, "positive",
         "my new release has my artist name misspelled, can you please take good care of it? <url>",
         "Hey! Congrats on the release. Your distributor can fix the spelling and resubmit the metadata; our artist team can help too: <url>",
         "Hey! Congrats on the release. Spelling fixes go through your distributor (they resubmit the metadata), and Spotify for Artists support can chase it: https://artists.spotify.com/help /AI"),
]
# fmt: on

DEV_IDS = {"g_002", "g_006", "g_009", "g_014", "g_017", "g_021", "g_026", "g_030", "g_034", "g_038", "g_041", "g_044", "g_050", "g_056", "g_058"}

# Judge flags the agent's reply earns on specific examples (hallucinated policy / promise / wrong issue).
AGENT_HALLUCINATED = {"g_007", "g_024", "g_033"}

FAILURE_MODES: list[dict[str, Any]] = [
    {
        "id": "fm1",
        "title": "Screenshot-only messages get confidently classified",
        "count": 5,
        "hypothesis": (
            "When the message is a few words plus an image, the model anchors on whatever word survives "
            "('do', 'this', 'seriously') and the retrieved neighbours, then invents a concrete issue. The "
            "media-only rule only fires on a bare <url>, so anything with a stray word slips past it."
        ),
        "examples": ["g_047", "g_051", "g_052"],
        "why": {
            "g_047": "Nothing in the text names an issue; the model borrowed 'restart the app' from the retrieved crash threads.",
            "g_051": "A single emoji and a link became a greyed-out-track answer because two neighbours were about new releases.",
            "g_052": "Guessed playback again, but confidence fell to 0.52 so the threshold rescued the decision, not the model.",
        },
        "proposed_fix": (
            "Extend the media-only rule to '<url> plus fewer than 4 content words', and add a judge-style "
            "self-check prompt field: 'what in the text supports this intent?' that must quote the message."
        ),
    },
    {
        "id": "fm2",
        "title": "Login, security and library problems blur together",
        "count": 6,
        "hypothesis": (
            "The same symptom (signed out, playlists missing, unfamiliar activity) has three different causes with "
            "three different decisions. The model classifies the symptom, not the cause, so it over-escalates "
            "harmless sign-outs and under-escalates real account takeovers."
        ),
        "examples": ["g_015", "g_018", "g_053"],
        "why": {
            "g_015": "A routine sign-out was read as account sharing; escalating it costs a human 10 minutes for nothing.",
            "g_018": "The customer literally asks 'did someone get into my account' and the model answered a playlist question. This is the costly miss.",
            "g_053": "'Playlists gone + on Free' is the textbook wrong-account login; the model went straight to playlist recovery.",
        },
        "proposed_fix": (
            "Add a rule for 'someone ... my account' phrasing, and give the prompt a decision table that lists "
            "the three causes side by side with their tell-tale phrases and the escalation each one needs."
        ),
    },
    {
        "id": "fm3",
        "title": "Money words in plan questions force needless escalations",
        "count": 11,
        "hypothesis": (
            "The money-keyword rule was written for disputes ('charged twice', 'refund') but also fires on "
            "prices and hypotheticals ('$9.99', 'don't want to get charged'). Because rules override the LLM, "
            "a correct intent and a good reply still end up in the human queue."
        ),
        "examples": ["g_027", "g_028", "g_054"],
        "why": {
            "g_027": "'$9.99' matched the currency pattern; the intent and the reply were both right.",
            "g_028": "'get charged' is a hypothetical, not a dispute, but the rule cannot tell tense.",
            "g_054": "'£14.99' fired; this is the single largest source of unnecessary escalations (11 of 14).",
        },
        "proposed_fix": (
            "Split the rule: currency + 'charged/billed/refund' in past tense forces escalation; a bare price or "
            "'how much / still $' becomes a soft flag the LLM can weigh. Re-tune the threshold on dev afterwards."
        ),
    },
    {
        "id": "fm4",
        "title": "Non-English messages with English product words get an English fix",
        "count": 7,
        "hypothesis": (
            "Brand nouns (Discover Weekly, Alexa, Spotify Connect, premium) are the same in every language, so "
            "BM25 retrieves English troubleshooting threads and the model follows the evidence instead of "
            "noticing the customer wrote in Spanish or Indonesian."
        ),
        "examples": ["g_045", "g_046", "g_055"],
        "why": {
            "g_045": "'premium' and 'kartu' (card) pulled billing neighbours; a billing escalation for a language redirect.",
            "g_046": "'connect' and 'alexa' dominate the tokens; the reply is correct troubleshooting in the wrong language.",
            "g_055": "Right diagnosis, wrong language: the customer gets an English answer the historical brand never gave.",
        },
        "proposed_fix": (
            "Run a cheap language check before retrieval (stopword ratio already exists in the data layer) and "
            "short-circuit to the language-redirect template when English stopwords are under 15%."
        ),
    },
    {
        "id": "fm5",
        "title": "Replies promise what the evidence never did",
        "count": 8,
        "hypothesis": (
            "When the retrieved replies are vague ('DM us'), the model fills the gap with plausible policy: "
            "a refund, a device limit, a help-article URL. The judge caught these as hallucinated policy; "
            "they read fine and would embarrass the brand."
        ),
        "examples": ["g_024", "g_033", "g_007"],
        "why": {
            "g_024": "'We'll refund the difference' commits the brand to money it never promised in any thread.",
            "g_033": "The help-article URL does not exist in the evidence or the link map; it was composed.",
            "g_007": "'3,333-song limit' is a 2017 fact from the model's memory, not from the cited thread.",
        },
        "proposed_fix": (
            "Constrain links to the resolved_links of cited evidence (post-validate and strip unknown URLs), "
            "and add 'never promise refunds or credits' to the safety section of the system prompt."
        ),
    },
]

DECISIONS: list[dict[str, str]] = [
    {
        "title": "Judge with a different model than the agent",
        "decision": "Replies are scored by gemini-2.5-pro while the agent runs on gemini-2.5-flash.",
        "why": "Models rate their own writing style higher; using a different judge removes the most obvious self-preference bias at the cost of a slower, rate-limited judge pass.",
    },
    {
        "title": "Treat escalate as the positive class and optimise recall first",
        "decision": "The headline escalation metric is recall of gold escalations; precision is reported but not optimised.",
        "why": "A missed escalation means an auto-posted reply to a hacked or over-charged customer; an unnecessary one costs a human a few minutes. The costs are asymmetric, so the metric should be too.",
    },
    {
        "title": "Rules override the LLM, never the reverse",
        "decision": "Deterministic keyword rules can force escalation; the LLM cannot un-escalate a rule hit.",
        "why": "Money, security and legal language are cheap to detect and catastrophic to miss. The price is a cluster of unnecessary escalations on plan questions, which is tracked as a failure mode rather than hidden.",
    },
    {
        "title": "Tune the confidence threshold on the dev split only",
        "decision": "The 0.60 intent-confidence threshold was chosen on 50 dev examples; every reported number uses the remaining 150.",
        "why": "Reporting metrics on the same examples used to pick the threshold would quietly inflate recall. Fifty examples is a coarse dial, so the sweep is shown rather than just the chosen point.",
    },
    {
        "title": "BM25 over embeddings for retrieval",
        "decision": "Historical threads are retrieved with BM25 over cleaned customer text; no embedding model is used.",
        "why": "Support tweets are short and vocabulary-driven (error codes, product names); BM25 matched them well, builds in seconds, runs offline and keeps the pipeline reproducible without another API.",
    },
    {
        "title": "Exclude the example's own thread from retrieval",
        "decision": "When evaluating a golden example, its own thread id is removed from the BM25 candidates.",
        "why": "Every golden message exists in the corpus with its real brand reply. Without exclusion the agent would copy the answer key and the grounding scores would be meaningless.",
    },
    {
        "title": "Commit the LLM cache so results replay without a key",
        "decision": "Every Gemini call is stored in cache/llm_cache.sqlite keyed by a hash of model, prompt and schema; the file is committed.",
        "why": "A reviewer should reproduce the headline numbers in minutes without an API key or quota. It also makes the evaluation deterministic across runs.",
    },
    {
        "title": "Judge all three replies in one comparative call",
        "decision": "The judge sees the agent, nearest-neighbour and template replies together, shuffled and labelled A/B/C.",
        "why": "Absolute 1 to 5 scores drift between calls; comparing side by side anchors the scale, and shuffling removes the position bias that would otherwise favour whichever reply appears first.",
    },
    {
        "title": "Sign every drafted reply with /AI",
        "decision": "Reply drafts end with the signature /AI instead of a human agent's initials.",
        "why": "SpotifyCares signs with agent initials; copying them would impersonate a person. The brand pattern is preserved while making the author honest.",
    },
    {
        "title": "Stratify the golden sample by keyword bucket plus a random slice",
        "decision": "Candidates were sampled per intent-keyword bucket, with a quarter drawn uniformly at random.",
        "why": "Pure random sampling gives a handful of security or billing cases; pure keyword sampling hides messages the keywords miss. The random slice keeps an honest estimate of the long tail.",
    },
    {
        "title": "Label twice and adjudicate, even with one author",
        "decision": "Every golden example was labelled in two separate passes a week apart, with disagreements adjudicated and recorded.",
        "why": "It is not independent inter-annotator agreement, and the report says so, but it surfaces genuinely ambiguous examples (31 of 200) that a single pass would have silently guessed.",
    },
    {
        "title": "Ship the UI with a static mode fed by exported JSON",
        "decision": "The dashboard reads public/data/*.json when VITE_STATIC=1 and only calls the API in live mode.",
        "why": "Reviewers can open the results on GitHub Pages without running Python, and the same UI works against the FastAPI server for the live playground and human rating flow.",
    },
]

CAVEAT_TEMPLATES: list[str] = [
    "Both label passes were done by the same person a week apart. κ = {intent_kappa:.2f} measures self-consistency, not independent agreement, and probably overstates label reliability.",
    "The test split has {n_test} examples. The 95% CI on macro-F1 is {f1_ci_width:.0f} points wide, so the agent's lead over the LLM zero-shot baseline is real but its size is not settled.",
    "The judge is a Gemini model scoring another Gemini model. On the {n_pairs} human-rated pairs it agreed moderately (κ = {judge_kappa:.2f}) and scored the agent's replies about {judge_bias:.1f} points higher than the human did.",
    "Escalation recall of {recall:.2f} is bought with {unnecessary} unnecessary escalations, {money_rule} of them from the money-keyword rule firing on plan questions. Without that rule the auto-handle rate would be {auto_without:.2f}.",
    "Grounding means 'matches what SpotifyCares said in 2017'. Several replies scored well while pointing at help articles that have since moved, and the agent inherits every policy the brand had then.",
]


def _round(x: float, nd: int = 4) -> float:
    return float(round(float(x), nd))


class Rules:
    """Deterministic rule engine driven by config/escalation.yaml (mirror of cadence.agent.rules)."""

    def __init__(self) -> None:
        cfg = escalation_config()
        self.threshold: float = float(cfg["confidence_threshold"])
        self.rules = [
            (
                r["flag"],
                bool(r["force_escalate"]),
                r["reason_code"],
                r["reason"],
                [re.compile(p, re.IGNORECASE) for p in r["patterns"]],
            )
            for r in cfg["rules"]
        ]
        self.soft = [(s["flag"], [re.compile(p, re.IGNORECASE) for p in s["patterns"]]) for s in cfg["soft_flags"]]

    def apply(self, text: str) -> dict[str, Any]:
        flags: list[str] = []
        soft_flags: list[str] = []
        forced: tuple[str, str] | None = None
        for flag, force, code, reason, patterns in self.rules:
            if any(p.search(text) for p in patterns):
                flags.append(flag)
                if force and forced is None:
                    forced = (code, reason)
        for flag, patterns in self.soft:
            if any(p.search(text) for p in patterns):
                soft_flags.append(flag)
        return {
            "flags": flags,
            "soft_flags": soft_flags,
            "force_escalate": forced is not None,
            "reason_code": forced[0] if forced else None,
            "reason": forced[1] if forced else None,
        }


def keyword_intent(text: str, intents: list[dict[str, Any]]) -> str:
    """The `simple_keyword` baseline (CONTRACT §15.1, config/intents.yaml v1 header).

    Keywords shorter than five characters match on word boundaries, longer ones as substrings; the intent
    with the most hits wins, ties go to the earlier intent in the file, no hit -> other.
    """
    low = text.lower()
    best, best_n = "other", 0
    for intent in intents:
        n = 0
        for raw in intent.get("keywords", []):
            k = str(raw).lower()
            if len(k) < 5:
                n += len(re.findall(rf"{re.escape(k)}", low))
            else:
                n += low.count(k)
        if n > best_n:
            best, best_n = intent["id"], n
    return best


def reason_text(code: str, intent_name: str) -> str:
    return {
        "billing_dispute": "Customer disputes or cannot complete a payment; billing needs a human with account access.",
        "account_security": "Signs of unauthorised account access; security cases are always handled by a person.",
        "needs_account_lookup": "Resolving this requires looking at the account backstage, which the agent cannot do.",
        "high_frustration_or_churn": "Repeated contact with an explicit churn threat; a human should own this conversation.",
        "legal_or_safety": "Legal or safety language detected; requires human handling.",
        "ambiguous_or_media_only": "The issue cannot be determined from the text alone; a human needs to look at the media.",
        "low_confidence": "Intent confidence is below the tuned threshold, so the draft should be reviewed before posting.",
        "out_of_scope": "Not a support request the brand can act on publicly.",
    }.get(code, f"Escalated for {intent_name.lower()}.")


def random_tco(rng: np.random.Generator) -> str:
    alphabet = string.ascii_letters + string.digits
    return "https://t.co/" + "".join(rng.choice(list(alphabet)) for _ in range(10))


class MockBuilder:
    """Builds every JSON file from SPECS and the config files."""

    def __init__(self) -> None:
        self.rng = np.random.default_rng(SEED)
        self.rules = Rules()
        cfg = intents_config()
        self.intents: list[dict[str, Any]] = cfg["intents"]
        self.intent_ids: list[str] = [i["id"] for i in self.intents]
        self.intent_name = {i["id"]: i["name"] for i in self.intents}
        models = models_config()
        self.agent_model: str = models["agent_model"]
        self.judge_model: str = models["judge_model"]
        self.zero_shot_model: str = models["zero_shot_model"]
        self.ids = [f"g_{i + 1:03d}" for i in range(len(SPECS))]
        self.spec_by_id = dict(zip(self.ids, SPECS, strict=True))
        self.thread_ids: dict[str, str] = {}
        self.created: dict[str, str] = {}
        self._assign_threads()

    # ------------------------------------------------------------------ golden
    def _assign_threads(self) -> None:
        start = datetime(2017, 10, 5, tzinfo=timezone.utc)
        base_ids = np.sort(self.rng.choice(np.arange(2_200_000, 2_900_000, 37), size=len(self.ids), replace=False))
        for gid, tid in zip(self.ids, base_ids, strict=True):
            self.thread_ids[gid] = f"t_{int(tid)}"
            when = start + timedelta(days=int(self.rng.integers(0, 56)), hours=int(self.rng.integers(6, 24)), minutes=int(self.rng.integers(0, 60)))
            self.created[gid] = when.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _raw(self, text: str) -> str:
        raw = text.replace("<url>", random_tco(self.rng))
        return f"@SpotifyCares {raw}".strip()

    def _thread(self, gid: str, spec: Spec) -> list[dict[str, Any]]:
        opener = int(self.thread_ids[gid][2:])
        t0 = datetime.strptime(self.created[gid], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        sig = str(self.rng.choice(["JI", "NS", "AK", "MR", "LD", "TP", "CB"]))
        turns: list[dict[str, Any]] = [
            {"role": "customer", "tweet_id": opener, "created_at": self.created[gid], "text": spec.text},
            {
                "role": "brand",
                "tweet_id": opener + 1,
                "created_at": (t0 + timedelta(minutes=int(self.rng.integers(4, 95)))).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "text": spec.hist,
                "agent_sig": sig,
            },
        ]
        if spec.follow == "fixed":
            follow_c, follow_b = "that worked, thank you!!", "Glad to hear it! Have a good one 🎶"
        elif spec.follow == "still":
            follow_c, follow_b = "tried that, still the same 😕", "Thanks for trying. Can you DM us your username and device model? We'll dig in backstage"
        else:
            return turns
        t2 = t0 + timedelta(hours=int(self.rng.integers(2, 30)))
        turns.append({"role": "customer", "tweet_id": opener + 2, "created_at": t2.strftime("%Y-%m-%dT%H:%M:%SZ"), "text": follow_c})
        turns.append({"role": "brand", "tweet_id": opener + 3, "created_at": (t2 + timedelta(minutes=41)).strftime("%Y-%m-%dT%H:%M:%SZ"), "text": follow_b, "agent_sig": sig})
        return turns

    def _annotation(self, spec: Spec, override: dict[str, Any]) -> dict[str, Any]:
        base = {
            "intent": spec.intent,
            "should_escalate": spec.escalate,
            "escalation_reason_code": spec.reason,
            "sentiment": spec.sentiment,
            "media_only": spec.media_only,
            "notes": spec.notes,
        }
        base.update(override)
        return base

    def golden(self, gid: str, spec: Spec) -> dict[str, Any]:
        ann_a = self._annotation(spec, spec.ann_a)
        ann_b = self._annotation(spec, spec.ann_b)
        agreement = {"intent": ann_a["intent"] == ann_b["intent"], "should_escalate": ann_a["should_escalate"] == ann_b["should_escalate"]}
        bucket = "random" if int(gid[2:]) % 5 == 0 else f"kw:{spec.intent.split('_')[0]}"
        return {
            "id": gid,
            "thread_id": self.thread_ids[gid],
            "split": "dev" if gid in DEV_IDS else "test",
            "text": spec.text,
            "text_raw": self._raw(spec.text),
            "created_at": self.created[gid],
            "historical_brand_reply": spec.hist,
            "historical_thread": self._thread(gid, spec),
            "gold": {
                "intent": spec.intent,
                "secondary_intent": spec.secondary,
                "should_escalate": spec.escalate,
                "escalation_reason_code": spec.reason,
                "sentiment": spec.sentiment,
                "media_only": spec.media_only,
                "notes": spec.notes,
            },
            "annotations": {"a": ann_a, "b": ann_b},
            "agreement": agreement,
            "adjudicated": not (agreement["intent"] and agreement["should_escalate"]),
            "sampling_bucket": bucket,
        }

    # ------------------------------------------------------------- predictions
    def _neighbours(self, gid: str, intent: str, k: int = 3) -> list[str]:
        same = [g for g in self.ids if g != gid and self.spec_by_id[g].intent == intent]
        others = [g for g in self.ids if g != gid and g not in same]
        pool = same + others
        return pool[:k] if len(same) >= k else same + list(self.rng.choice(others, size=k - len(same), replace=False))

    def _evidence(self, gid: str, intent: str, n_cited: int) -> list[dict[str, Any]]:
        hits = self._neighbours(gid, intent)
        base = float(self.rng.uniform(12.5, 16.5))
        out = []
        for i, other in enumerate(hits):
            sp = self.spec_by_id[other]
            score = base - i * float(self.rng.uniform(1.6, 3.2))
            links = [RESOLVED_LINK_BY_INTENT[sp.intent]] if "<url>" in sp.hist else []
            out.append(
                {
                    "thread_id": self.thread_ids[other],
                    "score": _round(score, 2),
                    "customer_text": sp.text,
                    "brand_reply": sp.hist,
                    "resolved_links": links,
                    "cited": i < n_cited,
                }
            )
        return out

    def _base_response(self, gid: str, system: str, spec: Spec, model: str) -> dict[str, Any]:
        return {
            "id": gid,
            "system": system,
            "input_text": spec.text,
            "intent": spec.intent,
            "intent_confidence": None,
            "secondary_intent": None,
            "sentiment": spec.sentiment,
            "reply_draft": "",
            "citations": [],
            "grounding_notes": "",
            "decision": "auto_handle",
            "escalation": None,
            "rule_flags": [],
            "evidence": [],
            "model": model,
            "latency_ms": 0,
            "cached": True,
            "trace": None,
        }

    def agent(self, gid: str, spec: Spec) -> dict[str, Any]:
        rule = self.rules.apply(spec.text)
        intent = spec.agent_intent or spec.intent
        conf = spec.agent_conf if spec.agent_conf is not None else _round(self.rng.uniform(0.66, 0.97), 2)
        llm_decision = spec.agent_decision or ("escalate" if spec.escalate else "auto_handle")
        llm_code = spec.agent_reason or (spec.reason if llm_decision == "escalate" else None)
        if llm_decision == "escalate" and llm_code is None:
            llm_code = "needs_account_lookup"
        forced = rule["force_escalate"]
        below = conf < self.rules.threshold
        decision = "escalate" if (forced or llm_decision == "escalate" or below) else "auto_handle"
        if forced:
            code, reason = rule["reason_code"], rule["reason"]
        elif llm_decision == "escalate":
            code, reason = llm_code, reason_text(str(llm_code), self.intent_name[intent])
        elif below:
            code, reason = "low_confidence", reason_text("low_confidence", self.intent_name[intent])
        else:
            code, reason = None, None
        n_cited = 1 if decision == "escalate" else int(self.rng.integers(1, 3))
        evidence = self._evidence(gid, intent, n_cited)
        cited = [e["thread_id"] for e in evidence if e["cited"]]
        retrieval_ms = int(self.rng.integers(7, 26))
        llm_ms = int(self.rng.integers(880, 2300))
        if forced:
            notes = f"Rules forced escalation ({rule['flags'][0]}); the draft only invites a DM and mirrors {cited[0]}'s reply."
        elif decision == "escalate":
            notes = f"Retrieved threads ({', '.join(cited)}) all end in a DM hand-off for this kind of issue; no self-serve step is grounded."
        else:
            notes = f"Steps mirror the first brand reply in {cited[0]} ({self.intent_name[self.spec_by_id[self._neighbours(gid, intent)[0]].intent]}); link is the one resolved from that thread."
        resp = self._base_response(gid, "agent", spec, self.agent_model)
        resp.update(
            {
                "intent": intent,
                "intent_confidence": conf,
                "secondary_intent": spec.secondary,
                "reply_draft": spec.agent_reply,
                "citations": cited,
                "grounding_notes": notes,
                "decision": decision,
                "escalation": {"reason_code": code, "reason": reason} if decision == "escalate" else None,
                "rule_flags": rule["flags"] + rule["soft_flags"],
                "evidence": evidence,
                "latency_ms": retrieval_ms + llm_ms + int(self.rng.integers(3, 12)),
                "cached": bool(self.rng.random() < 0.9),
                "trace": {
                    "retrieval_ms": retrieval_ms,
                    "llm_ms": llm_ms,
                    "prompt_tokens": int(self.rng.integers(1750, 2650)),
                    "output_tokens": int(self.rng.integers(170, 330)),
                    "llm_decision": llm_decision,
                    "llm_reason_code": llm_code,
                    "forced_by_rules": forced,
                },
            }
        )
        return resp

    def trivial(self, gid: str, spec: Spec, majority: str) -> dict[str, Any]:
        resp = self._base_response(gid, "trivial", spec, "none")
        resp.update(
            {
                "intent": majority,
                "sentiment": "neutral",
                "reply_draft": TRIVIAL_TEMPLATE,
                "decision": "escalate",
                "escalation": {"reason_code": "low_confidence", "reason": "trivial baseline escalates everything"},
                "grounding_notes": "Most common historical brand template (reply_templates.json[0]).",
                "latency_ms": 0,
            }
        )
        return resp

    def _perturb(self, gold: str, p_correct: float) -> str:
        if self.rng.random() < p_correct:
            return gold
        options = CONFUSABLE[gold]
        weights = np.array([0.55, 0.3, 0.15][: len(options)])
        return str(self.rng.choice(options, p=weights / weights.sum()))

    def simple(self, gid: str, spec: Spec) -> dict[str, Any]:
        rule = self.rules.apply(spec.text)
        intent = self._perturb(spec.intent, 0.64)
        nn_id = self._neighbours(gid, spec.intent, k=1)[0]
        nn = self.spec_by_id[nn_id]
        resp = self._base_response(gid, "simple", spec, "tfidf_lr+bm25")
        resp.update(
            {
                "intent": intent,
                "intent_confidence": _round(self.rng.uniform(0.31, 0.78), 2),
                "sentiment": "neutral",
                "reply_draft": nn.hist,
                "citations": [self.thread_ids[nn_id]],
                "grounding_notes": f"Verbatim first brand reply of BM25 top-1 thread {self.thread_ids[nn_id]}.",
                "decision": "escalate" if rule["force_escalate"] else "auto_handle",
                "escalation": {"reason_code": rule["reason_code"], "reason": rule["reason"]} if rule["force_escalate"] else None,
                "rule_flags": rule["flags"] + rule["soft_flags"],
                "evidence": [
                    {
                        "thread_id": self.thread_ids[nn_id],
                        "score": _round(self.rng.uniform(9.5, 15.5), 2),
                        "customer_text": nn.text,
                        "brand_reply": nn.hist,
                        "resolved_links": [RESOLVED_LINK_BY_INTENT[nn.intent]] if "<url>" in nn.hist else [],
                        "cited": True,
                    }
                ],
                "latency_ms": int(self.rng.integers(6, 21)),
            }
        )
        return resp

    def simple_keyword(self, gid: str, spec: Spec, simple_resp: dict[str, Any]) -> dict[str, Any]:
        resp = dict(simple_resp)
        resp["system"] = "simple_keyword"
        resp["intent"] = keyword_intent(spec.text, self.intents)
        resp["intent_confidence"] = None
        resp["model"] = "keywords+bm25"
        return resp

    def zero_shot(self, gid: str, spec: Spec) -> dict[str, Any]:
        intent = self._perturb(spec.intent, 0.76)
        gold_decision = "escalate" if spec.escalate else "auto_handle"
        flip = self.rng.random() < 0.14
        decision = ("auto_handle" if gold_decision == "escalate" else "escalate") if flip else gold_decision
        default = next(i for i in self.intents if i["id"] == intent)
        code = spec.reason if (decision == "escalate" and not flip and spec.reason) else default.get("default_reason_code", "low_confidence")
        resp = self._base_response(gid, "llm_zero_shot", spec, self.zero_shot_model)
        resp.update(
            {
                "intent": intent,
                "intent_confidence": _round(self.rng.uniform(0.55, 0.96), 2),
                "sentiment": str(self.rng.choice([spec.sentiment, spec.sentiment, "neutral"])),
                "decision": decision,
                "escalation": {"reason_code": code, "reason": reason_text(str(code), self.intent_name[intent])} if decision == "escalate" else None,
                "grounding_notes": "Zero-shot: taxonomy + policy in the prompt, no retrieval, 10 messages per call.",
                "latency_ms": int(self.rng.integers(120, 340)),
                "trace": {
                    "retrieval_ms": 0,
                    "llm_ms": int(self.rng.integers(110, 330)),
                    "prompt_tokens": int(self.rng.integers(210, 290)),
                    "output_tokens": int(self.rng.integers(28, 44)),
                    "llm_decision": decision,
                    "llm_reason_code": code if decision == "escalate" else None,
                    "forced_by_rules": False,
                },
            }
        )
        return resp

    # -------------------------------------------------------------------- judge
    def _judge_row(self, gid: str, system: str, scores: dict[str, int], flags: dict[str, bool], rationale: str) -> dict[str, Any]:
        overall = scores["overall"]
        verdict = "ship" if overall >= 4 and not any(flags.values()) else ("reject" if overall <= 2 else "edit")
        rated = datetime(2026, 9, 8, 18, 0, tzinfo=timezone.utc) + timedelta(seconds=int(self.rng.integers(0, 9000)))
        return {
            "id": gid,
            "system": system,
            "rater": self.judge_model,
            "scores": scores,
            "flags": flags,
            "verdict": verdict,
            "rationale": rationale,
            "rated_at": rated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def judge_agent(self, gid: str, spec: Spec, pred: dict[str, Any]) -> dict[str, Any]:
        gold_decision = "escalate" if spec.escalate else "auto_handle"
        wrong_issue = pred["intent"] != spec.intent and not (spec.intent == PL and pred["intent"] == PB)
        hallucinated = gid in AGENT_HALLUCINATED
        if pred["decision"] == "auto_handle" and gold_decision == "escalate":
            scores = {"grounded": 3, "resolves": 1, "tone": 4, "safe": 3, "overall": 2}
            rationale = "Confident, on-brand and about the wrong problem: the customer's real issue needs a human, and the reply would post publicly without one."
        elif hallucinated:
            scores = {"grounded": 2, "resolves": 4, "tone": 5, "safe": 2 if gid == "g_024" else 4, "overall": 3}
            rationale = {
                "g_007": "Tone and steps match the neighbour threads, but the 3,333-song limit appears nowhere in the evidence.",
                "g_024": "Warm and specific, yet it promises a refund no historical reply ever made; that is a commitment the brand did not authorise.",
                "g_033": "The midnight-release explanation is grounded; the help-article URL is not in any cited thread or the link map.",
            }[gid]
        elif wrong_issue:
            scores = {"grounded": 3, "resolves": 2, "tone": 4, "safe": 5, "overall": 2}
            rationale = "Well-formed troubleshooting for a problem the customer did not describe; the language or the issue was misread."
        elif pred["decision"] == "escalate":
            scores = {"grounded": 5, "resolves": 4, "tone": 5, "safe": 5, "overall": int(self.rng.choice([4, 4, 5]))}
            rationale = "Correctly hands off to a DM without promising an outcome; matches how SpotifyCares handled the retrieved threads."
        else:
            overall = int(self.rng.choice([4, 4, 5, 5, 5]))
            scores = {"grounded": int(self.rng.choice([4, 5, 5])), "resolves": int(self.rng.choice([3, 4, 5])), "tone": int(self.rng.choice([4, 5, 5])), "safe": 5, "overall": overall}
            rationale = str(
                self.rng.choice(
                    [
                        "Every step is traceable to the cited thread's reply; concise, one concrete action, under 280 characters.",
                        "Mirrors the brand's greeting-plus-step pattern and cites a link that resolves in the link map. Could be one sentence shorter.",
                        "Addresses the exact symptom with the same fix the brand used historically; tone is warm without grovelling.",
                    ]
                )
            )
        flags = {"hallucinated_link_or_policy": hallucinated, "asks_sensitive_info": False, "wrong_issue": wrong_issue or (pred["decision"] == "auto_handle" and gold_decision == "escalate")}
        return self._judge_row(gid, "agent", scores, flags, rationale)

    def judge_simple(self, gid: str, spec: Spec, pred: dict[str, Any]) -> dict[str, Any]:
        nn_intent = self.spec_by_id[next(g for g in self.ids if self.thread_ids[g] == pred["citations"][0])].intent
        same = nn_intent == spec.intent
        overall = int(self.rng.choice([3, 3, 4] if same else [1, 2, 2, 3]))
        scores = {"grounded": 4, "resolves": max(1, overall - 1), "tone": 4, "safe": 5 if "<url>" not in pred["reply_draft"] else 4, "overall": overall}
        flags = {"hallucinated_link_or_policy": bool("<url>" in pred["reply_draft"] and self.rng.random() < 0.3), "asks_sensitive_info": False, "wrong_issue": not same or overall <= 2}
        rationale = (
            "A real historical reply about the same kind of issue, so it is grounded by construction, but it answers the neighbour's specifics rather than this customer's."
            if same
            else "Verbatim brand reply to a different problem; polite, safe, and unrelated to what the customer asked."
        )
        return self._judge_row(gid, "simple", scores, flags, rationale)

    def judge_trivial(self, gid: str) -> dict[str, Any]:
        overall = int(self.rng.choice([1, 1, 2, 2, 3]))
        scores = {"grounded": 3, "resolves": 1 if overall < 3 else 2, "tone": 4, "safe": 5, "overall": overall}
        flags = {"hallucinated_link_or_policy": False, "asks_sensitive_info": False, "wrong_issue": overall <= 2}
        return self._judge_row(
            gid,
            "trivial",
            scores,
            flags,
            "The generic DM template: safe and on-brand, but it resolves nothing and ignores the message entirely.",
        )

    # ------------------------------------------------------------- golden_merged
    def build_golden_merged(self) -> list[dict[str, Any]]:
        majority = max(self.intent_ids, key=lambda i: sum(s.intent == i for s in SPECS))
        rows: list[dict[str, Any]] = []
        for gid, spec in zip(self.ids, SPECS, strict=True):
            for reply in (spec.agent_reply, spec.hist):
                if len(reply) > 280:
                    raise ValueError(f"{gid}: reply exceeds 280 chars ({len(reply)})")
            row = self.golden(gid, spec)
            agent = self.agent(gid, spec)
            simple = self.simple(gid, spec)
            row["predictions"] = {
                "agent": agent,
                "trivial": self.trivial(gid, spec, majority),
                "simple": simple,
                "simple_keyword": self.simple_keyword(gid, spec, simple),
                "llm_zero_shot": self.zero_shot(gid, spec),
            }
            row["judge"] = {
                "agent": self.judge_agent(gid, spec, agent),
                "simple": self.judge_simple(gid, spec, simple),
                "trivial": self.judge_trivial(gid),
            }
            rows.append(row)
        return rows

    # -------------------------------------------------------------- eval summary
    def _confusion(self, support: dict[str, int], acc: dict[str, float]) -> np.ndarray:
        n = len(self.intent_ids)
        idx = {k: i for i, k in enumerate(self.intent_ids)}
        m = np.zeros((n, n), dtype=int)
        for gold, s in support.items():
            errors = int(round(s * (1 - acc[gold])))
            m[idx[gold], idx[gold]] = s - errors
            options = CONFUSABLE[gold]
            weights = np.array([0.55, 0.3, 0.15][: len(options)])
            for _ in range(errors):
                m[idx[gold], idx[str(self.rng.choice(options, p=weights / weights.sum()))]] += 1
        return m

    @staticmethod
    def _expand(matrix: np.ndarray, labels: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
        gold, pred = [], []
        for i, g in enumerate(labels):
            for j, p in enumerate(labels):
                gold.extend([g] * int(matrix[i, j]))
                pred.extend([p] * int(matrix[i, j]))
        return np.array(gold), np.array(pred)

    def _intent_metrics(self, gold: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
        labels = self.intent_ids
        per_class: dict[str, dict[str, float | int]] = {}
        f1s, supports = [], []
        for lab in labels:
            tp = int(np.sum((gold == lab) & (pred == lab)))
            fp = int(np.sum((gold != lab) & (pred == lab)))
            fn = int(np.sum((gold == lab) & (pred != lab)))
            p = tp / (tp + fp) if tp + fp else 0.0
            r = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * p * r / (p + r) if p + r else 0.0
            support = int(np.sum(gold == lab))
            per_class[lab] = {"precision": _round(p), "recall": _round(r), "f1": _round(f1), "support": support}
            f1s.append(f1)
            supports.append(support)
        weights = np.array(supports) / max(1, sum(supports))
        return {
            "accuracy": _round(float(np.mean(gold == pred))),
            "macro_f1": _round(float(np.mean(f1s))),
            "weighted_f1": _round(float(np.sum(np.array(f1s) * weights))),
            "per_class": per_class,
        }

    @staticmethod
    def _bootstrap(stat: Callable[[np.ndarray], np.ndarray], n: int, reps: int = 1000) -> list[float]:
        """95% percentile interval of `stat`, which maps a (reps, n) resample-index matrix to (reps,) values."""
        rng = np.random.default_rng(SEED)
        idx = rng.integers(0, n, size=(reps, n))
        vals = np.asarray(stat(idx), dtype=float)
        return [_round(float(np.percentile(vals, 2.5))), _round(float(np.percentile(vals, 97.5)))]

    def _macro_f1_rows(self, gold: np.ndarray, pred: np.ndarray) -> np.ndarray:
        """Macro-F1 for each row of two (reps, n) integer-coded label matrices."""
        per_label = []
        for code in range(len(self.intent_ids)):
            g, p = gold == code, pred == code
            tp = (g & p).sum(axis=1)
            fp = (~g & p).sum(axis=1)
            fn = (g & ~p).sum(axis=1)
            precision = np.where(tp + fp > 0, tp / np.maximum(tp + fp, 1), 0.0)
            recall = np.where(tp + fn > 0, tp / np.maximum(tp + fn, 1), 0.0)
            per_label.append(np.where(precision + recall > 0, 2 * precision * recall / np.maximum(precision + recall, 1e-12), 0.0))
        return np.mean(np.stack(per_label), axis=0)

    def intent_block(self) -> dict[str, Any]:
        support = {NE: 10, SEC: 7, BIL: 16, LG: 14, DL: 10, MD: 7, CON: 14, PL: 12, PB: 22, SUB: 13, FR: 11, OT: 14}
        if set(support) != set(self.intent_ids):
            raise ValueError(f"support keys {sorted(support)} do not match config/intents.yaml {sorted(self.intent_ids)}")
        base = {k: 0.86 for k in self.intent_ids}
        acc_by_system: dict[str, dict[str, float]] = {
            "agent": {**base, OT: 0.57, NE: 0.7, LG: 0.79, PL: 0.77, SEC: 0.71, SUB: 0.86, MD: 0.71},
            "llm_zero_shot": {**{k: 0.79 for k in self.intent_ids}, OT: 0.5, NE: 0.6, LG: 0.71, PL: 0.69, SEC: 0.71, MD: 0.57},
            "simple_tfidf_lr": {**{k: 0.64 for k in self.intent_ids}, SEC: 0.29, NE: 0.5, OT: 0.36, DL: 0.55, FR: 0.5, MD: 0.29},
            "simple_keyword": {**{k: 0.68 for k in self.intent_ids}, OT: 0.36, FR: 0.45, NE: 0.8, SEC: 0.57, PL: 0.5, MD: 0.71},
        }
        systems: dict[str, Any] = {}
        for system, acc in acc_by_system.items():
            m = self._confusion(support, acc)
            gold, pred = self._expand(m, self.intent_ids)
            metrics = self._intent_metrics(gold, pred)
            n = len(gold)
            metrics["confusion"] = {"labels": list(self.intent_ids), "matrix": m.tolist()}
            codes = {label: i for i, label in enumerate(self.intent_ids)}
            g_codes = np.array([codes[x] for x in gold])
            p_codes = np.array([codes[x] for x in pred])
            metrics["ci95"] = {
                "accuracy": self._bootstrap(lambda ix, g=g_codes, p=p_codes: (g[ix] == p[ix]).mean(axis=1), n),
                "macro_f1": self._bootstrap(lambda ix, g=g_codes, p=p_codes: self._macro_f1_rows(g[ix], p[ix]), n),
            }
            systems[system] = metrics
        gold_all = np.array([k for k, s in support.items() for _ in range(s)])
        majority = max(support, key=support.__getitem__)
        m_triv = np.zeros((len(self.intent_ids), len(self.intent_ids)), dtype=int)
        for k, s in support.items():
            m_triv[self.intent_ids.index(k), self.intent_ids.index(majority)] = s
        pred_triv = np.array([majority] * len(gold_all))
        triv = self._intent_metrics(gold_all, pred_triv)
        triv["confusion"] = {"labels": list(self.intent_ids), "matrix": m_triv.tolist()}
        triv["ci95"] = {"accuracy": [_round(support[majority] / 150 - 0.055), _round(support[majority] / 150 + 0.06)], "macro_f1": [_round(triv["macro_f1"] - 0.006), _round(triv["macro_f1"] + 0.007)]}
        ordered = {"agent": systems["agent"], "trivial_majority": triv, "simple_keyword": systems["simple_keyword"], "simple_tfidf_lr": systems["simple_tfidf_lr"], "llm_zero_shot": systems["llm_zero_shot"]}
        return {"labels": list(self.intent_ids), "support": support, "systems": ordered}

    def escalation_block(self) -> dict[str, Any]:
        n, n_pos = 150, 62
        gold = np.array([True] * n_pos + [False] * (n - n_pos))

        def make(tp: int, fp: int) -> np.ndarray:
            pred = np.zeros(n, dtype=bool)
            pred[:tp] = True
            pred[n_pos : n_pos + fp] = True
            return pred

        def metrics(pred: np.ndarray, reason_acc: float, missed: list[str]) -> dict[str, Any]:
            tp = int(np.sum(gold & pred))
            fp = int(np.sum(~gold & pred))
            fn = int(np.sum(gold & ~pred))
            tn = int(np.sum(~gold & ~pred))
            p = tp / (tp + fp) if tp + fp else 0.0
            r = tp / (tp + fn) if tp + fn else 0.0
            f1 = 2 * p * r / (p + r) if p + r else 0.0

            def rec(ix: np.ndarray) -> np.ndarray:
                g, q = gold[ix], pred[ix]
                return (g & q).sum(axis=1) / np.maximum(g.sum(axis=1), 1)

            def prec(ix: np.ndarray) -> np.ndarray:
                g, q = gold[ix], pred[ix]
                return (g & q).sum(axis=1) / np.maximum(q.sum(axis=1), 1)

            return {
                "precision": _round(p),
                "recall": _round(r),
                "f1": _round(f1),
                "auto_handle_rate": _round(float(np.mean(~pred))),
                "accuracy": _round(float(np.mean(gold == pred))),
                "missed_escalations": fn,
                "unnecessary_escalations": fp,
                "reason_code_accuracy": _round(reason_acc),
                "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
                "ci95": {
                    "recall": self._bootstrap(rec, n),
                    "precision": self._bootstrap(prec, n),
                    "auto_handle_rate": self._bootstrap(lambda ix: (~pred[ix]).mean(axis=1), n),
                },
                "missed_examples": missed,
            }

        agent_pred = make(58, 14)
        systems = {
            "agent": metrics(agent_pred, 0.862, ["g_018", "g_047", "g_051", "g_053"]),
            "trivial_always_escalate": metrics(make(62, 88), 0.0, []),
            "trivial_never_escalate": metrics(make(0, 0), 0.0, ["g_005", "g_011", "g_012", "g_013", "g_016", "g_017", "g_018", "g_019", "g_020", "g_021", "g_022", "g_023", "g_024", "g_047", "g_048", "g_049", "g_051", "g_052", "g_053"]),
            "simple_rules": metrics(make(46, 9), 0.783, ["g_012", "g_013", "g_018", "g_019", "g_047", "g_049", "g_051", "g_052", "g_053"]),
            "llm_zero_shot": metrics(make(52, 20), 0.731, ["g_013", "g_018", "g_047", "g_051", "g_053"]),
        }
        thresholds = [round(0.30 + 0.05 * i, 2) for i in range(13)]
        recall_curve = [0.871, 0.887, 0.903, 0.919, 0.919, 0.935, None, 0.952, 0.968, 0.968, 0.984, 0.984, 1.0]
        precision_curve = [0.871, 0.859, 0.848, 0.838, 0.826, 0.817, None, 0.786, 0.759, 0.732, 0.703, 0.667, 0.621]
        auto_curve = [0.587, 0.58, 0.573, 0.567, 0.553, 0.54, None, 0.493, 0.453, 0.42, 0.373, 0.327, 0.28]
        chosen = systems["agent"]
        sweep = [
            {
                "threshold": t,
                "recall": _round(chosen["recall"] if r is None else r, 3),
                "precision": _round(chosen["precision"] if p is None else p, 3),
                "auto_handle_rate": _round(chosen["auto_handle_rate"] if a is None else a, 3),
            }
            for t, r, p, a in zip(thresholds, recall_curve, precision_curve, auto_curve, strict=True)
        ]
        return {"systems": systems, "threshold_sweep": sweep}

    def reply_quality_block(self) -> dict[str, Any]:
        n = 150
        dists = {"agent": [3, 8, 19, 61, 59], "nn_reply": [24, 45, 50, 24, 7], "trivial_template": [58, 60, 24, 8, 0]}
        flag_counts = {
            "agent": {"hallucinated_link_or_policy": 8, "asks_sensitive_info": 1, "wrong_issue": 9},
            "nn_reply": {"hallucinated_link_or_policy": 3, "asks_sensitive_info": 0, "wrong_issue": 63},
            "trivial_template": {"hallucinated_link_or_policy": 0, "asks_sensitive_info": 0, "wrong_issue": 118},
        }
        offsets = {
            "agent": {"grounded": 0.15, "resolves": -0.2, "tone": 0.45, "safe": 0.65},
            "nn_reply": {"grounded": 1.1, "resolves": -0.4, "tone": 0.9, "safe": 1.6},
            "trivial_template": {"grounded": 1.0, "resolves": -0.6, "tone": 1.9, "safe": 2.9},
        }
        systems: dict[str, Any] = {}
        overall_arrays: dict[str, np.ndarray] = {}
        for system, dist in dists.items():
            overall = np.repeat(np.arange(1, 6), dist)
            self.rng.shuffle(overall)
            overall_arrays[system] = overall
            means = {"overall": _round(float(overall.mean()), 3)}
            for dim, off in offsets[system].items():
                means[dim] = _round(float(np.clip(overall + off, 1, 5).mean()), 3)
            flagged = np.zeros(n, dtype=bool)
            any_flag = max(flag_counts[system].values())
            flagged[np.argsort(overall)[:any_flag]] = True
            ship = float(np.mean((overall >= 4) & ~flagged))
            systems[system] = {
                "mean": {k: means[k] for k in JUDGE_DIMS},
                "dist_overall": dist,
                "ship_rate": _round(ship, 3),
                "flag_rates": {k: _round(v / n, 3) for k, v in flag_counts[system].items()},
                "ci95": {"overall": self._bootstrap(lambda ix, o=overall: o[ix].mean(axis=1), n)},
            }
        agent, nn, triv = overall_arrays["agent"], overall_arrays["nn_reply"], overall_arrays["trivial_template"]
        pairwise = {
            "agent_vs_nn_win_rate": _round(float(np.mean(agent > nn) + 0.5 * np.mean(agent == nn)), 3),
            "agent_vs_trivial_win_rate": _round(float(np.mean(agent > triv) + 0.5 * np.mean(agent == triv)), 3),
        }
        return {"systems": systems, "pairwise": pairwise}

    @staticmethod
    def _weighted_kappa(a: np.ndarray, b: np.ndarray, k: int = 5) -> float:
        o = np.zeros((k, k))
        for x, y in zip(a, b, strict=True):
            o[x - 1, y - 1] += 1
        w = np.array([[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)])
        e = np.outer(o.sum(1), o.sum(0)) / o.sum()
        return float(1 - (w * o).sum() / (w * e).sum())

    @staticmethod
    def _rank(a: np.ndarray) -> np.ndarray:
        """Average ranks (1-based), ties share the mean rank, as in scipy.stats.rankdata."""
        order = np.argsort(a, kind="stable")
        ranks = np.empty(len(a), dtype=float)
        i = 0
        while i < len(a):
            j = i
            while j + 1 < len(a) and a[order[j + 1]] == a[order[i]]:
                j += 1
            ranks[order[i : j + 1]] = (i + j) / 2 + 1
            i = j + 1
        return ranks

    @classmethod
    def _spearman(cls, a: np.ndarray, b: np.ndarray) -> float:
        """Spearman ρ = Pearson correlation of the average ranks."""
        return float(np.corrcoef(cls._rank(a), cls._rank(b))[0, 1])

    def judge_agreement_block(self, merged: list[dict[str, Any]]) -> dict[str, Any]:
        test = [r for r in merged if r["split"] == "test"]
        pairs: list[dict[str, Any]] = []
        humans = {d: [] for d in JUDGE_DIMS}
        judges = {d: [] for d in JUDGE_DIMS}
        for system in JUDGED_SYSTEMS:
            chosen = self.rng.choice(len(test), size=20, replace=False)
            for i in sorted(chosen):
                row = test[i]
                js = row["judge"][system]["scores"]
                for dim in JUDGE_DIMS:
                    noise = int(self.rng.choice([-2, -1, 0, 1, 2], p=[0.09, 0.28, 0.39, 0.18, 0.06]))
                    if system == "agent" and dim == "overall" and self.rng.random() < 0.55:
                        noise = min(noise, 0)
                    h = int(np.clip(js[dim] + noise, 1, 5))
                    humans[dim].append(h)
                    judges[dim].append(int(js[dim]))
                pairs.append({"id": row["id"], "system": system, "human": humans["overall"][-1], "judge": judges["overall"][-1]})
        h, j = np.array(humans["overall"]), np.array(judges["overall"])
        per_dim = {
            d: {"weighted_kappa": _round(self._weighted_kappa(np.array(humans[d]), np.array(judges[d])), 3), "spearman": _round(self._spearman(np.array(humans[d]), np.array(judges[d])), 3)}
            for d in JUDGE_DIMS
        }
        return {
            "n": len(pairs),
            "weighted_kappa_overall": _round(self._weighted_kappa(h, j), 3),
            "spearman_overall": _round(self._spearman(h, j), 3),
            "exact_agreement": _round(float(np.mean(h == j)), 3),
            "within_one": _round(float(np.mean(np.abs(h - j) <= 1)), 3),
            "judge_minus_human_mean": _round(float((j - h).mean()), 3),
            "per_dimension": per_dim,
            "pairs": pairs,
        }

    def build_eval_summary(self, merged: list[dict[str, Any]]) -> dict[str, Any]:
        intent = self.intent_block()
        escalation = self.escalation_block()
        reply = self.reply_quality_block()
        agreement = self.judge_agreement_block(merged)
        agent_intent = intent["systems"]["agent"]
        agent_esc = escalation["systems"]["agent"]
        agent_reply = reply["systems"]["agent"]
        money_rule = next(fm["count"] for fm in FAILURE_MODES if fm["id"] == "fm3")
        caveats = [
            t.format(
                intent_kappa=0.79,
                n_test=150,
                f1_ci_width=(agent_intent["ci95"]["macro_f1"][1] - agent_intent["ci95"]["macro_f1"][0]) * 100,
                n_pairs=agreement["n"],
                judge_kappa=agreement["weighted_kappa_overall"],
                judge_bias=agreement["judge_minus_human_mean"],
                recall=agent_esc["recall"],
                unnecessary=agent_esc["unnecessary_escalations"],
                money_rule=money_rule,
                auto_without=agent_esc["auto_handle_rate"] + money_rule / 150,
            )
            for t in CAVEAT_TEMPLATES
        ]
        return {
            "meta": {
                "brand": "SpotifyCares",
                "n_golden": 200,
                "n_dev": 50,
                "n_test": 150,
                "generated_at": GENERATED_AT,
                "agent_model": self.agent_model,
                "judge_model": self.judge_model,
                "zero_shot_model": self.zero_shot_model,
                "git_sha": "mock-data",
                "cache_hit_rate": 0.97,
                "threshold": self.rules.threshold,
                "caveats": caveats,
                "dataset": {
                    "n_openers": 26068,
                    "n_brand_tweets": 43265,
                    "n_rows_total": 2811774,
                    "n_brands": 108,
                    "date_from": "2017-04-07",
                    "date_to": "2017-12-13",
                    "share_english": 0.93,
                    "share_with_link": 0.14,
                    "share_single_reply": 0.72,
                    "n_resolved_links": 150,
                },
            },
            "headline": {
                "intent_macro_f1": agent_intent["macro_f1"],
                "escalation_recall": agent_esc["recall"],
                "auto_handle_rate": agent_esc["auto_handle_rate"],
                "judge_overall_mean": agent_reply["mean"]["overall"],
                "judge_overall_mean_nn": reply["systems"]["nn_reply"]["mean"]["overall"],
                "ci95": {
                    "intent_macro_f1": agent_intent["ci95"]["macro_f1"],
                    "escalation_recall": agent_esc["ci95"]["recall"],
                    "auto_handle_rate": agent_esc["ci95"]["auto_handle_rate"],
                    "judge_overall_mean": agent_reply["ci95"]["overall"],
                },
            },
            "intent": intent,
            "escalation": escalation,
            "reply_quality": {"systems": reply["systems"], "pairwise": reply["pairwise"]},
            "judge_agreement": agreement,
            "annotator_agreement": {"intent_kappa": 0.79, "intent_raw": 0.85, "escalation_kappa": 0.7, "escalation_raw": 0.88, "n_disagreements": 31},
            "cost": {"n_llm_calls": 640, "total_prompt_tokens": 1_384_220, "total_output_tokens": 171_905, "wall_minutes": 84.3},
        }

    # ------------------------------------------------------------ failure modes
    def build_failure_modes(self, merged: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {r["id"]: r for r in merged}
        out = []
        for fm in FAILURE_MODES:
            examples = []
            for gid in fm["examples"]:
                row = by_id[gid]
                pred = row["predictions"]["agent"]
                examples.append(
                    {
                        "golden_id": gid,
                        "text": row["text"],
                        "gold_intent": row["gold"]["intent"],
                        "pred_intent": pred["intent"],
                        "gold_decision": "escalate" if row["gold"]["should_escalate"] else "auto_handle",
                        "pred_decision": pred["decision"],
                        "reply_draft": pred["reply_draft"],
                        "why": fm["why"][gid],
                    }
                )
            out.append(
                {
                    "id": fm["id"],
                    "title": fm["title"],
                    "count": fm["count"],
                    "share": _round(fm["count"] / 150, 3),
                    "hypothesis": fm["hypothesis"],
                    "examples": examples,
                    "proposed_fix": fm["proposed_fix"],
                }
            )
        return out

    # ------------------------------------------------------------------ config
    def build_intents_json(self) -> list[dict[str, Any]]:
        return [
            {
                "id": i["id"],
                "name": i["name"],
                "description": " ".join(str(i["description"]).split()),
                "examples": list(i.get("examples", [])),
                "default_decision": i["default_decision"],
                "default_reason_code": i.get("default_reason_code"),
                "keywords": [str(k) for k in i.get("keywords", [])],
            }
            for i in self.intents
        ]

    def build_escalation_json(self) -> dict[str, Any]:
        cfg = escalation_config()
        return {
            "confidence_threshold": cfg["confidence_threshold"],
            "min_words_for_auto_handle": cfg["min_words_for_auto_handle"],
            "reason_codes": [{"id": r["id"], "name": r["name"], "description": " ".join(str(r["description"]).split())} for r in cfg["reason_codes"]],
            "rules": [
                {"flag": r["flag"], "force_escalate": bool(r["force_escalate"]), "reason_code": r["reason_code"], "reason": r["reason"], "n_patterns": len(r["patterns"])}
                for r in cfg["rules"]
            ],
            "soft_flags": [{"flag": s["flag"], "n_patterns": len(s["patterns"])} for s in cfg["soft_flags"]],
        }

    def build_health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "has_api_key": False,
            "cache_only": True,
            "agent_model": self.agent_model,
            "judge_model": self.judge_model,
            "cache_entries": 1412,
            "index_size": 26068,
            "n_golden": 200,
        }

    @staticmethod
    def build_decisions() -> list[dict[str, Any]]:
        return [{"n": i + 1, **d} for i, d in enumerate(DECISIONS)]


def write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build_all() -> dict[str, Any]:
    """Every mock file keyed by file name (deterministic for a fixed SEED)."""
    builder = MockBuilder()
    merged = builder.build_golden_merged()
    return {
        "golden_merged.json": merged,
        "eval_summary.json": builder.build_eval_summary(merged),
        "failure_modes.json": builder.build_failure_modes(merged),
        "decisions.json": builder.build_decisions(),
        "health.json": builder.build_health(),
        "intents.json": builder.build_intents_json(),
        "escalation.json": builder.build_escalation_json(),
    }


def main(argv: list[str] | None = None) -> int:
    """Generate all mock files (default target: ui/public/data; override with ``--out DIR``)."""
    parser = argparse.ArgumentParser(description="Generate Cadence UI mock data.")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output directory (default: ui/public/data)")
    args = parser.parse_args(argv)
    files = build_all()
    for name, obj in files.items():
        write(args.out / name, obj)
    print(f"wrote {len(files)} files to {args.out} ({len(files['golden_merged.json'])} golden examples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
