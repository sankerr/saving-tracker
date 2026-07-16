/* Saving Tracker — English / Hebrew i18n */
(function (global) {
  'use strict';

  var LANG_KEY = 'st_lang';
  var SUPPORTED = { en: true, he: true };

  var STRINGS = {
    en: {
      'auth.title.login': 'Sign in',
      'auth.title.register': 'Create account',
      'auth.subtitle.login': 'Enter your email and password to access your portfolio.',
      'auth.subtitle.register': 'Enter a valid email address and password. An admin must approve new accounts.',
      'auth.email': 'Email',
      'auth.emailPlaceholder': 'you@example.com',
      'auth.password': 'Password',
      'auth.submit.login': 'Sign in',
      'auth.submit.register': 'Create account',
      'auth.toggle.toRegister': 'Create an account',
      'auth.toggle.toLogin': 'Already have an account? Sign in',
      'auth.forgotNote': 'Forgot password? Sign in with a new account or ask your admin to reset it in the database.',
      'auth.viewTour': 'New here? Take a 2-minute tour →',
      'auth.error.signInFailed': 'Sign in failed',
      'auth.error.registerFailed': 'Registration failed',
      'auth.toast.accountCreated': 'Account created. An admin must approve your account before you can sign in.',

      'hero.eyebrow': 'Cloud · Private · Password Protected',
      'hero.title': 'Saving Tracker',
      'hero.subtitle': 'A personal portfolio notebook for Israeli pension/provident funds (gemelnet), RSU grants, ESPP, and cash — built for private tracking, not professional use.',

      'disclaimer.aria': 'Important disclaimers',
      'disclaimer.compact': 'Personal tool — not financial advice.',
      'disclaimer.title': 'Important — read before using',
      'nav.aria': 'Sections',
      'disclaimer.item.personalUse': '<strong>Personal use only.</strong> This app is a hobby tool for tracking your own savings. It is not a commercial product, regulated financial service, or substitute for a licensed advisor.',
      'disclaimer.item.notAdvice': '<strong>Not financial, investment, tax, or legal advice.</strong> All figures, charts, and projections are informational estimates. Do not make real-world decisions based solely on this app.',
      'disclaimer.item.noTax': '<strong>No tax calculation.</strong> Numbers are pre-tax and nominal. Israeli tax rules (CPI adjustment, Section 102, deposit ceilings, withholding, etc.) are not modeled — consult your fund manager, accountant, or Israel Tax Authority resources.',
      'disclaimer.item.dataStale': '<strong>Data may be wrong or stale.</strong> Fund yields come from data.gov.il; stock and FX prices from Yahoo Finance. Sources can be delayed, revised, or unavailable. Always verify against official statements.',
      'disclaimer.item.projections': '<strong>Projections are not promises.</strong> Past performance and assumed growth rates do not guarantee future results. What-if scenarios are simplified models, not forecasts.',
      'disclaimer.item.ownRisk': '<strong>Use at your own risk.</strong> The authors provide no warranty and accept no liability for losses or decisions arising from use of this software.',
      'disclaimer.item.responsibility': '<strong>Your responsibility.</strong> You are solely responsible for the accuracy of data you enter and for keeping your login credentials secure. New accounts require admin approval before access is granted.',

      'status.loading': 'Loading…',
      'status.wakingServer': 'Waking up server…',
      'status.syncing': 'Syncing…',
      'status.synced': 'Synced',
      'status.loadedUsdils': 'Loaded · USDILS {rate}',
      'status.failedLoad': 'Failed to load data',
      'status.syncFailed': 'Sync failed',
      'status.yields': 'Yields · {label}',

      'chrome.langToggle': 'Language',
      'chrome.aiChat': 'AI chat',
      'chrome.hideAi': 'Hide AI',
      'chrome.openAiChat': 'Open AI chat',
      'chrome.toggleTheme': 'Toggle light/dark mode',
      'chrome.signOut': 'Sign out',
      'chrome.refresh': '↻ Refresh',

      'common.cancel': 'Cancel',
      'common.save': 'Save',
      'common.show': 'Show',
      'common.hide': 'Hide',
      'common.gotIt': 'Got it',
      'common.details': 'Details',
      'common.confirm': 'Confirm',
      'common.failed': 'Failed',
      'common.updated': 'Updated',
      'common.deleted': 'Deleted',
      'help.aboutSection': 'What is this section?',

      'section.dashboard': 'Dashboard',
      'section.funds': 'Funds',
      'section.pension': 'Pension',
      'section.retirementSim': 'Retirement simulator',
      'section.rsu': 'RSU Grants',
      'section.espp': 'ESPP Plans',
      'section.cash': 'Cash & non-invested',
      'section.settings': 'Settings',

      'funds.add': '+ Add fund',
      'pension.add': '+ Add pension',
      'rsu.add': '+ Add grant',
      'espp.add': '+ Add plan',
      'cash.add': '+ Add cash',
      'pension.subtotal': 'Subtotal',
      'pension.excludedFromTotal': 'excluded from dashboard total',

      'dashboard.horizon': 'Horizon:',
      'dashboard.range': 'Range',
      'dashboard.resetRange': 'Reset range',
      'dashboard.whatIfGrow': 'If funds grow %/yr:',
      'dashboard.whatIfHint': 'funds only · cash + RSU + ESPP held flat',
      'dashboard.pensionNote': '<span>🔒</span><span><strong>Pension ({amount})</strong> is tracked separately below — not included in this total or the chart. The growth assumption above still applies to it, shown per row.</span>',
      'dashboard.caption': 'Default view shows the current month forward through your chosen horizon. Drag horizontally on the chart, or pick start/end months above to focus on a sub-range — any month works: past months pull in history, and picking far into the future automatically extends the projection (up to 50 years). Press Esc while dragging to cancel; click a horizon chip to reset.',

      'chat.title': 'Portfolio chat',
      'chat.panelAria': 'AI portfolio chat',
      'chat.clear': 'Clear',
      'chat.clearTitle': 'Clear conversation',
      'chat.close': 'Close chat',
      'chat.disclaimer': '<strong>AI chat disclaimer.</strong> Answers are generated by Google Gemini from a summary of your portfolio data. They are for personal education only — not financial, tax, investment, or legal advice. Figures may be incomplete or wrong; always verify against official statements. Messages and portfolio context are sent to Google’s API (free-tier terms may allow use to improve their products). Use at your own risk.',
      'chat.empty': 'Ask about your holdings, yields, allocation, or what to improve.',
      'chat.placeholder': 'Ask about your portfolio…',
      'chat.send': 'Send',
      'chat.sendAria': 'Send message',
      'chat.suggestionsAria': 'Suggested questions',
      'chat.chip.features': 'What can I do with this app?',
      'chat.chip.concentration': 'Where am I concentrated?',
      'chat.chip.improve': 'Improve my allocation?',
      'chat.chip.project': 'Project to May 2030 @ 8%',
      'chat.prompt.features': 'What can I do with this app? Summarize the main features and how to use them with my portfolio.',
      'chat.prompt.concentration': 'Where am I concentrated across funds, RSU, ESPP, and cash?',
      'chat.prompt.improve': 'Suggest concrete improvements based on my portfolio allocation, contributions, and vesting.',
      'chat.prompt.project': 'If my funds grow 8%/year, what is my projected portfolio total and change vs today by May 2030?',
      'chat.role.you': 'You',
      'chat.role.assistant': 'Assistant',
      'chat.thinking': 'Thinking…',
      'chat.disabled': 'Chat is disabled on the server.',
      'chat.sorry': 'Sorry — I could not answer that ({error}).',

      'settings.appearance': 'Appearance',
      'settings.theme.system': 'System (match device)',
      'settings.theme.light': 'Light',
      'settings.theme.dark': 'Dark',
      'settings.netOfFees': 'Default: MONTHLY_YIELD is net of fees',
      'settings.usdilsOverride': 'USDILS rate override',
      'settings.usdilsPlaceholder': 'leave blank to use Yahoo',
      'settings.exportJson': 'Export JSON',
      'settings.importJson': 'Import JSON',
      'settings.changePassword': 'Change password',
      'settings.clearCache': 'Clear cache',
      'settings.dangerZone': '<strong>Danger zone</strong> — permanent actions',
      'settings.deleteAccount': 'Delete my account',
      'settings.deleteAccountBlurb': 'Permanently deletes your login and all personal data from the database. This cannot be undone.',

      'toast.synced': 'Synced from data.gov.il + Yahoo',
      'toast.syncFailed': 'Sync failed',
      'toast.sessionExpired': 'Session expired. Please sign in again.',
      'toast.exported': 'Exported',
      'toast.imported': 'Imported',
      'toast.invalidJson': 'Invalid JSON',
      'toast.passwordUpdated': 'Password updated',
      'toast.passwordsMismatch': 'New passwords do not match',
      'toast.cacheCleared': 'Cache cleared. Click Refresh to resync.',
      'toast.accountDeleted': 'Your account was deleted.',
      'toast.fundAdded': 'Fund added',
      'toast.pensionAdded': 'Pension added',
      'toast.grantAdded': 'Grant added',
      'toast.esppAdded': 'ESPP plan added',
      'toast.cashAdded': 'Cash added',

      'help.dashboard.title': 'About the Dashboard',
      'help.chat.title': 'About AI chat',
      'help.funds.title': 'About Funds',
      'help.pension.title': 'About Pension',
      'help.retirementSim.title': 'About Retirement simulator',
      'help.rsu.title': 'About RSU Grants',
      'help.espp.title': 'About ESPP Plans',
      'help.cash.title': 'About Cash & non-invested',
      'help.settings.title': 'About Settings',

      'rsim.intro': 'Estimate pension vs. lump-sum choices at retirement using simplified 2026 Israeli rules. Nothing here is saved to your account.',
      'rsim.birthDate': 'Birth date',
      'rsim.gender': 'Gender',
      'rsim.gender.male': 'Male (גבר)',
      'rsim.gender.female': 'Female (אישה)',
      'rsim.retirementAge': 'Retirement age',
      'rsim.comprehensive': 'מקיפה balance at retirement (₪)',
      'rsim.supplementary': 'משלימה balance at retirement (₪, optional)',
      'rsim.targetPension': 'Target monthly pension — path 3 (₪)',
      'rsim.note': 'Informational estimate only — not tax or financial advice.',

      'help.dashboard.body': '<p>The big number is your <strong>total portfolio value</strong> in ILS — funds + RSU + ESPP + cash.</p>\n<p>The stacked chart looks forward from the current month. <code>If funds grow %/yr</code> applies to funds (and contributions) only; cash, RSU vesting, and ESPP stay flat on top.</p>\n<p><strong>Horizon chips</strong> and the date range (drag or pick months) control how far and which slice you see. Reset clears a custom range.</p>\n<p>Projections are estimates only — not advice.</p>',
      'help.chat.body': '<p>Optional assistant powered by <strong>Google Gemini</strong>. Opens as a right-side panel with a summary of your portfolio.</p>\n<p>Open with <strong>AI chat</strong> (desktop) or the floating <strong>AI</strong> button (mobile). History is session-only — use <strong>Clear</strong> to reset.</p>\n<p><strong>Not advice.</strong> Replies can be wrong. Messages and context go to Google’s API. Read the on-panel disclaimer.</p>',
      'help.funds.body': '<p>Israeli provident / study funds and savings policies from <code>data.gov.il</code> (gemelnet / ביטוח-נט).</p>\n<p>Each holding has an <strong>anchor period</strong> and <strong>anchor balance</strong>; the app compounds with published <code>MONTHLY_YIELD</code>.</p>\n<p>Use recurring rules for employee/employer deposits and manual events for one-offs. Fee estimates are informational — published yields are usually already net of fees.</p>',
      'help.pension.body': '<p>Israeli pension funds (<strong>קרן פנסיה</strong>) from pensia-net. Locked until retirement and <strong>excluded from the dashboard total</strong>.</p>\n<p>Same anchor + yield compounding as funds, with recurring contributions. What-if growth follows the dashboard assumption for pension only.</p>\n<p><strong>The app does not compute Israeli tax.</strong></p>',
      'help.retirementSim.body': '<p>Standalone what-if for Israeli pension withdrawal at retirement (2026 rules). <strong>Not linked</strong> to holdings and <strong>not saved</strong>.</p>\n<p>Enter מקיפה / optional משלימה balances, birth date, gender, and retirement age to compare pension vs lump-sum paths. Tax model is simplified.</p>',
      'help.rsu.body': '<p>Tracks ticker, grant date, shares, and vesting. Prices and FX from Yahoo Finance.</p>\n<p><strong>Held = vested − sold</strong>. Record sales for realized gain; cost basis defaults to grant-date close.</p>\n<p><strong>The app does not compute Israeli tax.</strong></p>',
      'help.espp.body': '<p>Employee Stock Purchase Plan: discount, lookback, offering length, and purchase lots.</p>\n<p>Discount captured and lookback bonus are computed per purchase; sales work like RSU (FIFO). Chart forecast stays flat at current value.</p>\n<p><strong>The app does not compute Israeli tax.</strong></p>',
      'help.cash.body': '<p>Money that counts toward your total but isn’t market-linked — savings, checking, deposits.</p>\n<p>Flat ILS or USD amounts (USD converts via Yahoo / override). Edit the amount when balances change. No compounding.</p>',
      'help.settings.body': '<p><strong>MONTHLY_YIELD is net of fees</strong>: leave on unless you have a specific reason.</p>\n<p><strong>USDILS override</strong>: pin FX; blank uses Yahoo.</p>\n<p><strong>Export / Import</strong> for backups. <strong>Clear cache</strong> drops market caches only — holdings are kept.</p>',
      'toast.exportFailed': 'Export failed',
      'status.deletingAccount': 'Deleting account…',
      'footer.credit': 'Saving Tracker — personal, non-commercial software. Not affiliated with fund managers, brokers, or data providers.',
      'funds.saveHolding': 'Save holding',
      'pension.save': 'Save pension',
      'rsu.save': 'Save grant',
      'espp.save': 'Save plan',
      'common.searchFund': 'Search by name, manager, or FUND_ID',
      'common.selectedFund': 'Selected fund',
      'common.nickname': 'Nickname',
      'common.balanceIls': 'Balance (₪)',
      'common.asOfPeriod': 'As of period',
      'common.netOfFees': 'MONTHLY_YIELD is net of fees',
      'common.tickerSearch': 'Ticker (search by symbol or company name)',
      'common.loadingOption': 'loading…',
      'funds.searchHint': 'Includes קופת גמל, קרן השתלמות, and פוליסות חיסכון (ביטוח-נט).',
      'funds.balanceHint': 'Use 0 if you\'re just starting this fund.',
      'funds.anchorHint': 'Pick the month your reported balance is for. Most pension/provident statements are end-of-previous-month — that\'s the default.',
      'funds.excludeFromDashboard': 'Exclude from dashboard',
      'funds.includeInDashboard': 'Include in dashboard',
      'funds.excludedBadge': 'not in dashboard',
      'funds.excludedGroupLabel': 'Excluded from dashboard',
      'funds.excludedToast': 'Excluded from the dashboard total',
      'funds.includedToast': 'Included in the dashboard total',
      'pension.anchorHint': 'Same anchor convention as Funds. v1 doesn\'t model recurring payroll deposits — re-anchor periodically when you get a new statement.',
      'rsu.grantDate': 'Grant date',
      'rsu.totalShares': 'Total shares',
      'rsu.vestingStart': 'Vesting start',
      'rsu.vestingMonths': 'Vesting months',
      'rsu.cliffMonths': 'Cliff months',
      'rsu.cadence': 'Cadence',
      'rsu.cadence.monthly': 'monthly',
      'rsu.cadence.quarterly': 'quarterly',
      'rsu.grantPriceOverride': 'Grant price override (USD/share)',
      'rsu.grantPricePlaceholder': 'blank = market close on grant date',
      'rsu.overrideHint': 'Override only if your company reported a different FMV (e.g. 30-day average or board-approved value). Leave blank to use Yahoo\'s closing price on the grant date — that\'s the cost basis Yahoo and most US brokers use.',
      'espp.discount': 'Discount %',
      'espp.offering': 'Offering length (months)',
      'espp.lookback': 'Plan has lookback (discount applied to lower of period-start / period-end price)',
      'cash.amount': 'Amount',
      'cash.currency': 'Currency',
      'cash.note': 'Note',
      'doc.title': 'Saving Tracker'
    },

    he: {
      'auth.title.login': 'התחברות',
      'auth.title.register': 'יצירת חשבון',
      'auth.subtitle.login': 'הזינו אימייל וסיסמה כדי לגשת לתיק.',
      'auth.subtitle.register': 'הזינו אימייל וסיסמה תקפים. מנהל חייב לאשר חשבונות חדשים.',
      'auth.email': 'אימייל',
      'auth.emailPlaceholder': 'you@example.com',
      'auth.password': 'סיסמה',
      'auth.submit.login': 'התחברות',
      'auth.submit.register': 'יצירת חשבון',
      'auth.toggle.toRegister': 'יצירת חשבון',
      'auth.toggle.toLogin': 'כבר יש לכם חשבון? התחברות',
      'auth.forgotNote': 'שכחתם סיסמה? התחברו עם חשבון חדש או בקשו ממנהל לאפס במסד הנתונים.',
      'auth.viewTour': 'חדשים כאן? צפו בסיור קצר ←',
      'auth.error.signInFailed': 'ההתחברות נכשלה',
      'auth.error.registerFailed': 'ההרשמה נכשלה',
      'auth.toast.accountCreated': 'החשבון נוצר. מנהל חייב לאשר לפני התחברות.',

      'hero.eyebrow': 'ענן · פרטי · מוגן בסיסמה',
      'hero.title': 'מעקב חיסכון',
      'hero.subtitle': 'מחברת תיק אישית לקופות גמל/השתלמות (גמלנט), מענקי RSU, ESPP ומזומן — למעקב פרטי, לא לשימוש מקצועי.',

      'disclaimer.aria': 'הבהרות חשובות',
      'disclaimer.compact': 'כלי אישי — לא ייעוץ פיננסי.',
      'disclaimer.title': 'חשוב — קראו לפני השימוש',
      'nav.aria': 'ניווט בין חלקים',
      'disclaimer.item.personalUse': '<strong>לשימוש אישי בלבד.</strong> זו אפליקציית תחביב למעקב אחר החיסכון שלכם. זו אינה מוצר מסחרי, שירות פיננסי מוסדר או תחליף ליועץ מוסמך.',
      'disclaimer.item.notAdvice': '<strong>לא ייעוץ פיננסי, השקעות, מס או משפטי.</strong> כל המספרים, הגרפים והתחזיות הם הערכות מידעיות בלבד. אל תקבלו החלטות רק על סמך האפליקציה.',
      'disclaimer.item.noTax': '<strong>אין חישוב מס.</strong> המספרים הם לפני מס ובערכים נומינליים. כללי המס בישראל אינם מחושבים באפליקציה — התייעצו עם מנהל הקופה, רואה חשבון או רשות המסים.',
      'disclaimer.item.dataStale': '<strong>הנתונים עלולים להיות שגויים או לא מעודכנים.</strong> תשואות מגיעות מ-data.gov.il; מחירי מניות ושערי חליפין מ-Yahoo. תמיד אמתו מול דוחות רשמיים.',
      'disclaimer.item.projections': '<strong>תחזיות אינן הבטחה.</strong> ביצועי עבר ושיעורי צמיחה משוערים אינם מבטיחים תוצאות עתידיות. תרחישי what-if הם מודלים מפושטים.',
      'disclaimer.item.ownRisk': '<strong>השימוש באחריותכם.</strong> אין אחריות לנזקים או החלטות הנובעים משימוש בתוכנה.',
      'disclaimer.item.responsibility': '<strong>אחריותכם.</strong> אתם אחראים לדיוק הנתונים שהזנתם ולאבטחת פרטי ההתחברות. חשבונות חדשים דורשים אישור מנהל.',

      'status.loading': 'טוען…',
      'status.wakingServer': 'מעיר את השרת…',
      'status.syncing': 'מסנכרן…',
      'status.synced': 'סונכרן',
      'status.loadedUsdils': 'נטען · USDILS {rate}',
      'status.failedLoad': 'טעינת הנתונים נכשלה',
      'status.syncFailed': 'הסנכרון נכשל',
      'status.yields': 'תשואות · {label}',

      'chrome.langToggle': 'שפה',
      'chrome.aiChat': 'צ׳אט AI',
      'chrome.hideAi': 'הסתר AI',
      'chrome.openAiChat': 'פתח צ׳אט AI',
      'chrome.toggleTheme': 'החלף מצב בהיר/כהה',
      'chrome.signOut': 'התנתקות',
      'chrome.refresh': '↻ רענון',

      'common.cancel': 'ביטול',
      'common.save': 'שמירה',
      'common.show': 'הצג',
      'common.hide': 'הסתר',
      'common.gotIt': 'הבנתי',
      'common.details': 'פרטים',
      'common.confirm': 'אישור',
      'common.failed': 'נכשל',
      'common.updated': 'עודכן',
      'common.deleted': 'נמחק',
      'help.aboutSection': 'מה זה החלק הזה?',

      'section.dashboard': 'לוח בקרה',
      'section.funds': 'קופות',
      'section.pension': 'פנסיה',
      'section.retirementSim': 'סימולטור פרישה',
      'section.rsu': 'מענקי RSU',
      'section.espp': 'תוכניות ESPP',
      'section.cash': 'מזומן ולא מושקע',
      'section.settings': 'הגדרות',

      'funds.add': '+ הוספת קופה',
      'pension.add': '+ הוספת פנסיה',
      'rsu.add': '+ הוספת מענק',
      'espp.add': '+ הוספת תוכנית',
      'cash.add': '+ הוספת מזומן',
      'pension.subtotal': 'סכום ביניים',
      'pension.excludedFromTotal': 'לא נכלל בסך הכולל',

      'dashboard.horizon': 'אופק:',
      'dashboard.range': 'טווח',
      'dashboard.resetRange': 'איפוס טווח',
      'dashboard.whatIfGrow': 'אם הקופות צומחות %/שנה:',
      'dashboard.whatIfHint': 'קופות בלבד · מזומן + RSU + ESPP קבועים',
      'dashboard.pensionNote': '<span>🔒</span><span><strong>פנסיה ({amount})</strong> מנוהלת בנפרד למטה — לא נכללת בסך זה או בגרף. הנחת הצמיחה למעלה עדיין חלה עליה, לפי שורה.</span>',
      'dashboard.caption': 'ברירת המחדל מציגה מהחודש הנוכחי קדימה לפי האופק שבחרתם. גררו אופקית בגרף או בחרו חודשי התחלה/סיום למיקוד — כל חודש אפשרי: חודשים בעבר מושכים היסטוריה, ובחירה רחוקה בעתיד מרחיבה אוטומטית את התחזית (עד 50 שנה). לחצו Esc תוך כדי גרירה לביטול; לחצו על שבב אופק לאיפוס.',

      'chat.title': 'צ׳אט על התיק',
      'chat.panelAria': 'צ׳אט AI על התיק',
      'chat.clear': 'ניקוי',
      'chat.clearTitle': 'נקה שיחה',
      'chat.close': 'סגור צ׳אט',
      'chat.disclaimer': '<strong>הבהרת צ׳אט AI.</strong> התשובות נוצרות על ידי Google Gemini מסיכום נתוני התיק. ללימוד אישי בלבד — לא ייעוץ פיננסי, מס, השקעות או משפטי. המספרים עלולים להיות חלקיים או שגויים; אמתו מול דוחות רשמיים. הודעות והקשר נשלחים ל-API של Google. השימוש באחריותכם.',
      'chat.empty': 'שאלו על החזקות, תשואות, פיזור או איך לשפר.',
      'chat.placeholder': 'שאלו על התיק…',
      'chat.send': 'שליחה',
      'chat.sendAria': 'שלח הודעה',
      'chat.suggestionsAria': 'שאלות מוצעות',
      'chat.chip.features': 'מה אפשר לעשות באפליקציה?',
      'chat.chip.concentration': 'איפה הריכוז שלי?',
      'chat.chip.improve': 'איך לשפר את הפיזור?',
      'chat.chip.project': 'תחזית למאי 2030 ב־8%',
      'chat.prompt.features': 'מה אפשר לעשות באפליקציה הזו? סכמו את היכולות העיקריות ואיך להשתמש בהן עם התיק שלי.',
      'chat.prompt.concentration': 'איפה אני מרוכז בין קופות, RSU, ESPP ומזומן?',
      'chat.prompt.improve': 'הציעו שיפורים קונקרטיים לפי הפיזור, ההפקדות וההבשלה שלי.',
      'chat.prompt.project': 'אם הקופות צומחות ב־8% לשנה, מה הסך החזוי והשינוי מול היום במאי 2030?',
      'chat.role.you': 'את/ה',
      'chat.role.assistant': 'עוזר AI',
      'chat.thinking': 'חושב…',
      'chat.disabled': 'הצ׳אט מושבת בשרת.',
      'chat.sorry': 'מצטער — לא הצלחתי לענות ({error}).',

      'settings.appearance': 'מראה',
      'settings.theme.system': 'מערכת (לפי המכשיר)',
      'settings.theme.light': 'בהיר',
      'settings.theme.dark': 'כהה',
      'settings.netOfFees': 'ברירת מחדל: MONTHLY_YIELD נטו מעמלות',
      'settings.usdilsOverride': 'דריסת שער USDILS',
      'settings.usdilsPlaceholder': 'השאירו ריק לשימוש ב-Yahoo',
      'settings.exportJson': 'ייצוא JSON',
      'settings.importJson': 'ייבוא JSON',
      'settings.changePassword': 'שינוי סיסמה',
      'settings.clearCache': 'ניקוי מטמון',
      'settings.dangerZone': '<strong>אזור מסוכן</strong> — פעולות בלתי הפיכות',
      'settings.deleteAccount': 'מחיקת החשבון שלי',
      'settings.deleteAccountBlurb': 'מוחק לצמיתות את ההתחברות ואת <strong>כל הנתונים האישיים</strong> במסד (החזקות, מענקים, מזומן, הגדרות ומחירי מטמון). לא ניתן לבטל.',

      'toast.synced': 'סונכרן מ-data.gov.il + Yahoo',
      'toast.syncFailed': 'הסנכרון נכשל',
      'toast.sessionExpired': 'פג תוקף ההתחברות. התחברו שוב.',
      'toast.exported': 'הנתונים יוצאו',
      'toast.imported': 'הנתונים יובאו',
      'toast.invalidJson': 'JSON לא תקין',
      'toast.passwordUpdated': 'הסיסמה עודכנה',
      'toast.passwordsMismatch': 'הסיסמאות החדשות אינן תואמות',
      'toast.cacheCleared': 'המטמון נוקה. לחצו רענון לסנכרון מחדש.',
      'toast.accountDeleted': 'החשבון נמחק.',
      'toast.fundAdded': 'הקופה נוספה',
      'toast.pensionAdded': 'הפנסיה נוספה',
      'toast.grantAdded': 'המענק נוסף',
      'toast.esppAdded': 'תוכנית ESPP נוספה',
      'toast.cashAdded': 'המזומן נוסף',

      'help.dashboard.title': 'על לוח הבקרה',
      'help.chat.title': 'על צ׳אט AI',
      'help.funds.title': 'על קופות',
      'help.pension.title': 'על פנסיה',
      'help.retirementSim.title': 'על סימולטור פרישה',
      'help.rsu.title': 'על מענקי RSU',
      'help.espp.title': 'על תוכניות ESPP',
      'help.cash.title': 'על מזומן ולא מושקע',
      'help.settings.title': 'על הגדרות',

      'rsim.intro': 'הערכת פנסיה מול משיכה חד־פעמית בפרישה לפי כללי ישראל מפושטים ל־2026. שום דבר כאן לא נשמר לחשבון.',
      'rsim.birthDate': 'תאריך לידה',
      'rsim.gender': 'מגדר',
      'rsim.gender.male': 'זכר (גבר)',
      'rsim.gender.female': 'נקבה (אישה)',
      'rsim.retirementAge': 'גיל פרישה',
      'rsim.comprehensive': 'יתרת מקיפה בפרישה (₪)',
      'rsim.supplementary': 'יתרת משלימה בפרישה (₪, אופציונלי)',
      'rsim.targetPension': 'יעד פנסיה חודשית — מסלול 3 (₪)',
      'rsim.note': 'הערכה מידעית בלבד — לא ייעוץ מס או פיננסי.',

      'help.dashboard.body': '<p>המספר הגדול הוא <strong>סך התיק</strong> בשקלים — קופות + RSU + ESPP + מזומן.</p>\n<p>הגרף המרובד מסתכל קדימה מהחודש הנוכחי. <code>אם הקופות צומחות %/שנה</code> חל על קופות (והפקדות) בלבד; מזומן, הבשלת RSU ו-ESPP נשארים קבועים.</p>\n<p><strong>שבבי אופק</strong> וטווח תאריכים (גרירה או בחירת חודשים) קובעים עד כמה רחוק ואיזה קטע רואים.</p>\n<p>תחזיות הן הערכות בלבד — לא ייעוץ.</p>',
      'help.chat.body': '<p>עוזר אופציונלי מבוסס <strong>Google Gemini</strong>. נפתח כפאנל בצד ימין עם סיכום התיק.</p>\n<p>פתיחה עם <strong>צ׳אט AI</strong> (מחשב) או כפתור <strong>AI</strong> הצף (מובייל). ההיסטוריה נשמרת רק לסשן — <strong>ניקוי</strong> מאפס.</p>\n<p><strong>לא ייעוץ.</strong> התשובות עלולות להיות שגויות. הודעות והקשר נשלחים ל-API של Google.</p>',
      'help.funds.body': '<p>קופות גמל / השתלמות ופוליסות חיסכון מ-<code>data.gov.il</code>.</p>\n<p>לכל החזקה יש <strong>תקופת עוגן</strong> ו<strong>יתרת עוגן</strong>; האפליקציה מצמידה לפי <code>MONTHLY_YIELD</code> שפורסם.</p>\n<p>כללי הפקדה חוזרים לעובד/מעסיק ואירועים ידניים לחד־פעמיים. הערכת עמלות למידע בלבד — התשואות בדרך כלל כבר נטו.</p>',
      'help.pension.body': '<p>קרנות פנסיה מ-pensia-net. נעולות עד פרישה ו<strong>לא נכללות בסך לוח הבקרה</strong>.</p>\n<p>אותו מנגנון עוגן + תשואה כמו בקופות, כולל הפקדות חוזרות. what-if לפי הנחת הצמיחה בלוח, לפנסיה בלבד.</p>\n<p><strong>האפליקציה אינה מחשבת מס ישראלי.</strong></p>',
      'help.retirementSim.body': '<p>כלי what-if עצמאי למשיכת פנסיה בפרישה (כללי 2026). <strong>לא מקושר</strong> להחזקות ו<strong>לא נשמר</strong>.</p>\n<p>הזינו יתרות מקיפה / משלימה, תאריך לידה, מגדר וגיל פרישה להשוואת מסלולים. מודל המס מפושט.</p>',
      'help.rsu.body': '<p>מעקב אחרי טיקר, תאריך מענק, מניות ולוח הבשלה. מחירים ושער מ-Yahoo.</p>\n<p><strong>מוחזק = הבשיל − נמכר</strong>. רשמו מכירות לרווח ממומש; בסיס עלות ברירת מחדל הוא מחיר הסגירה ביום המענק.</p>\n<p><strong>האפליקציה אינה מחשבת מס ישראלי.</strong></p>',
      'help.espp.body': '<p>תוכנית רכישת מניות לעובדים: הנחה, lookback, אורך מחזור ורכישות.</p>\n<p>הנחה שנתפסה ובונוס lookback מחושבים לרכישה; מכירות כמו RSU (FIFO). בגרף הראשי הערך נשאר שטוח.</p>\n<p><strong>האפליקציה אינה מחשבת מס ישראלי.</strong></p>',
      'help.cash.body': '<p>כסף שנכנס לסך התיק אך אינו קשור לשוק — חסכון, עו״ש, פיקדונות.</p>\n<p>סכומים שטוחים ב־ILS או USD (המרה דרך Yahoo / דריסה). ערכו את הסכום כשהיתרה משתנה. אין ריבית.</p>',
      'help.settings.body': '<p><strong>MONTHLY_YIELD נטו מעמלות</strong>: השאירו דלוק אלא אם יש סיבה ספציפית.</p>\n<p><strong>דריסת USDILS</strong>: קבעו שער; ריק = Yahoo.</p>\n<p><strong>ייצוא / ייבוא</strong> לגיבוי. <strong>ניקוי מטמון</strong> מוחק רק מטמוני שוק — ההחזקות נשמרות.</p>',
      'toast.exportFailed': 'הייצוא נכשל',
      'status.deletingAccount': 'מוחק חשבון…',
      'footer.credit': 'מעקב חיסכון — תוכנה אישית ולא מסחרית. ללא שיוך למנהלי קופות, ברוקרים או ספקי נתונים.',
      'funds.saveHolding': 'שמירת קופה',
      'pension.save': 'שמירת פנסיה',
      'rsu.save': 'שמירת מענק',
      'espp.save': 'שמירת תוכנית',
      'common.searchFund': 'חיפוש לפי שם, מנהל או FUND_ID',
      'common.selectedFund': 'הקופה שנבחרה',
      'common.nickname': 'כינוי',
      'common.balanceIls': 'יתרה (₪)',
      'common.asOfPeriod': 'נכון לתקופה',
      'common.netOfFees': 'MONTHLY_YIELD נטו מעמלות',
      'common.tickerSearch': 'טיקר (חיפוש לפי סימול או שם חברה)',
      'common.loadingOption': 'טוען…',
      'funds.searchHint': 'כולל קופת גמל, קרן השתלמות ופוליסות חיסכון (ביטוח-נט).',
      'funds.balanceHint': 'השתמשו ב-0 אם אתם רק מתחילים את הקופה.',
      'funds.anchorHint': 'בחרו את החודש שאליו מתייחסת היתרה המדווחת. רוב הדוחות של גמל/פנסיה הם לסוף החודש הקודם — זו ברירת המחדל.',
      'funds.excludeFromDashboard': 'הסתרה מהדשבורד',
      'funds.includeInDashboard': 'הצגה בדשבורד',
      'funds.excludedBadge': 'לא בדשבורד',
      'funds.excludedGroupLabel': 'לא נכללות בדשבורד',
      'funds.excludedToast': 'הקופה הוסתרה מסך הדשבורד',
      'funds.includedToast': 'הקופה נכללת בסך הדשבורד',
      'pension.anchorHint': 'אותה מוסכמת עוגן כמו בקופות. גרסה 1 אינה מודלת הפקדות שכר חוזרות — עגנו מחדש מדי פעם כשמגיע דוח חדש.',
      'rsu.grantDate': 'תאריך הענקה',
      'rsu.totalShares': 'סך מניות',
      'rsu.vestingStart': 'תחילת הבשלה',
      'rsu.vestingMonths': 'חודשי הבשלה',
      'rsu.cliffMonths': 'חודשי cliff',
      'rsu.cadence': 'תדירות',
      'rsu.cadence.monthly': 'חודשי',
      'rsu.cadence.quarterly': 'רבעוני',
      'rsu.grantPriceOverride': 'דריסת מחיר הענקה (USD למניה)',
      'rsu.grantPricePlaceholder': 'ריק = מחיר סגירה ביום ההענקה',
      'rsu.overrideHint': 'דרסו רק אם החברה דיווחה על FMV שונה (למשל ממוצע 30 יום או ערך שאושר בדירקטוריון). השאירו ריק כדי להשתמש במחיר הסגירה של Yahoo ביום ההענקה — זהו בסיס העלות שבו משתמשים Yahoo ורוב הברוקרים בארה״ב.',
      'espp.discount': 'אחוז הנחה',
      'espp.offering': 'אורך מחזור (חודשים)',
      'espp.lookback': 'לתוכנית יש lookback (ההנחה חלה על הנמוך מבין מחיר תחילת/סוף התקופה)',
      'cash.amount': 'סכום',
      'cash.currency': 'מטבע',
      'cash.note': 'הערה',
      'doc.title': 'מעקב חיסכון'
    }
  };

  function getLang() {
    var v = localStorage.getItem(LANG_KEY) || 'en';
    return SUPPORTED[v] ? v : 'en';
  }

  function t(key, vars) {
    var lang = getLang();
    var dict = STRINGS[lang] || STRINGS.en;
    var s = dict[key];
    if (s == null) s = (STRINGS.en && STRINGS.en[key]) || key;
    if (vars) {
      Object.keys(vars).forEach(function (k) {
        s = String(s).split('{' + k + '}').join(String(vars[k]));
      });
    }
    return s;
  }

  function applyDocumentLang(lang) {
    var root = document.documentElement;
    root.lang = lang;
    root.dir = lang === 'he' ? 'rtl' : 'ltr';
    document.title = t('doc.title');
  }

  function applyI18n(root) {
    root = root || document;
    root.querySelectorAll('[data-i18n]').forEach(function (el) {
      var key = el.getAttribute('data-i18n');
      if (!key) return;
      var html = el.hasAttribute('data-i18n-html');
      if (html) el.innerHTML = t(key);
      else el.textContent = t(key);
    });
    root.querySelectorAll('[data-i18n-placeholder]').forEach(function (el) {
      el.setAttribute('placeholder', t(el.getAttribute('data-i18n-placeholder')));
    });
    root.querySelectorAll('[data-i18n-title]').forEach(function (el) {
      el.setAttribute('title', t(el.getAttribute('data-i18n-title')));
    });
    root.querySelectorAll('[data-i18n-aria-label]').forEach(function (el) {
      el.setAttribute('aria-label', t(el.getAttribute('data-i18n-aria-label')));
    });
    root.querySelectorAll('[data-i18n-prompt]').forEach(function (el) {
      el.setAttribute('data-prompt', t(el.getAttribute('data-i18n-prompt')));
    });
    updateLangToggleButtons();
  }

  function updateLangToggleButtons() {
    var lang = getLang();
    var label = lang === 'he' ? 'EN' : 'עב';
    document.querySelectorAll('[data-lang-toggle]').forEach(function (btn) {
      btn.textContent = label;
      btn.setAttribute('title', t('chrome.langToggle'));
      btn.setAttribute('aria-label', t('chrome.langToggle'));
    });
  }

  function setLang(lang, opts) {
    opts = opts || {};
    if (!SUPPORTED[lang]) lang = 'en';
    localStorage.setItem(LANG_KEY, lang);
    applyDocumentLang(lang);
    applyI18n(document);
    if (typeof opts.onChange === 'function') opts.onChange(lang);
  }

  function toggleLang(opts) {
    setLang(getLang() === 'he' ? 'en' : 'he', opts);
  }

  function initLangBoot() {
    applyDocumentLang(getLang());
  }

  global.I18N = {
    LANG_KEY: LANG_KEY,
    STRINGS: STRINGS,
    t: t,
    getLang: getLang,
    setLang: setLang,
    toggleLang: toggleLang,
    applyI18n: applyI18n,
    initLangBoot: initLangBoot,
    updateLangToggleButtons: updateLangToggleButtons
  };
})(typeof window !== 'undefined' ? window : this);
