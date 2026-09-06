# تقرير دورة الأرشفة القانونية الخاصة — 6 سبتمبر 2026

> **نطاق التنفيذ:** المستودع الخاص `drrabab-almobi-dot/smart-legal-researcher-archive`، وعلى فرع `collector-import` فقط. لم يُمس فرع `main`، ولم تُكتب أي بيانات إلى قاعدة RABAB LEGAL AI، ولم يُفعّل البحث القانوني العام أو التنزيل العام.

## النتيجة التنفيذية

استُكملت دورة جمع قانونية فعلية وفق حواجز **Legal Archive Collector**. فُحصت قناة Telegram العامة، وروابط مجموعات أحكام وزارة العدل، وبوابة تعاميم الوزارة، وصفحات ديوان المظالم، وصفحات رسمية أو مسجلة للملكية الفكرية والأونسيترال والجمعية الفقهية السعودية. أسفر الفحص عن استرداد **24 أصل PDF رسميًا من وزارة العدل** كانت معلنة في سجل المصدر ولكن غير موجودة فعليًا في الفرع. طابقت جميع الملفات المقبولة SHA-256 المعلن قبل إدخالها، بإجمالي 94,778,131 بايت.

تضم الأصول الجديدة **23 مدونة أحكام** و**فهرسًا مرجعيًا واحدًا** هو الجزء 30 لعام 1434هـ. أُعيد استخدام 981 نطاق صفحات قائمًا في فهرس الباحثة لفصل **981 ملف PDF مستقلًا** دون تغيير صفحات الأصل، وبقيت جميع السجلات في مسار المراجعة الخاص وغير مؤهلة للبحث أو التنزيل العام. لم يُحسب الفهرس حكمًا مستقلًا.

## المصادر التي فُحصت

| المصدر | نطاق الفحص | النتيجة |
|---|---:|---|
| قناة Telegram العامة `@robiai33` | 1 صفحة تزايدية حتى حد المخزون | لا مرفقات جديدة؛ أعلى منشور 1335، و1085 صف بيانات وصفية، وصفر ملفات ثنائية |
| روابط مجموعات أحكام وزارة العدل | 44 رابط PDF رسميًا | 24 أصلًا جديدًا مطابقًا، 19 أصلًا موجودًا مطابقًا، وحالة اسم واحدة ببصمة مختلفة |
| بوابة تعاميم وزارة العدل | 339 معرفًا حاليًا | تطابق كامل مع 339 معرفًا مؤرشفًا؛ لا معرفات جديدة ولا مرفق PDF جديد مثبت |
| ديوان المظالم | 4 صفحات رسمية | نجح تأكيد النص لثلاث صفحات، لكن فشل النقل المباشر/الثنائي بسبب TLS وإغلاق الاتصال |
| الهيئة السعودية للملكية الفكرية | صفحة نشر القرارات | تأكدت الصفحة الرسمية؛ لم يظهر أصل PDF مطابق جديد |
| الأونسيترال | صفحة الوثيقة `A/CN.9/SER.C/ABSTRACTS/231` | تأكدت البيانات الوصفية؛ لم يُقبل مرشح لا يطابق بصمة الأصل المعلن |
| الجمعية الفقهية السعودية | صفحة السوابق في عقود المعاوضات التجارية | تأكد العنوان والمؤلف؛ لم يظهر رابط PDF قابل للاستخراج |

## الأصول الرسمية الجديدة

حُفظ كل ملف بالاسم المعلن دون تعديل. يمثل رابط المصدر ورابط المصدر الرسمي الرابط نفسه في هذه الدفعة لأنه تنزيل مباشر من نطاق وزارة العدل.

| الاسم الأصلي | النوع | الحجم (بايت) | الصفحات | SHA-256 | تاريخ الاستلام | رابط المصدر الرسمي |
|---|---|---:|---:|---|---|---|
| `moj-judgments-1434-volume-3.pdf` | مدونة أحكام | 5,898,258 | 380 | `9c54034ce7d443535fdf40305b5ae8f64a1adb54cd89ff928d7040b006bb7fef` | `2026-09-06T11:50:03+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/3.pdf) |
| `moj-judgments-1434-volume-4.pdf` | مدونة أحكام | 4,858,612 | 356 | `47d4c5054697335c8926799bd75ca40e51c5ddb31286a024defb7310e90e713e` | `2026-09-06T11:50:13+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/4.pdf) |
| `moj-judgments-1434-volume-6.pdf` | مدونة أحكام | 4,364,841 | 410 | `d8164d23575435d9de8ae23e628410450521627312e060d519a1d069c0675e11` | `2026-09-06T11:50:20+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/6.pdf) |
| `moj-judgments-1434-volume-7.pdf` | مدونة أحكام | 2,681,939 | 380 | `f5f2ad3c10d624ba478a766336b07bf999780bbca7c373f94c22b15ddcaea611` | `2026-09-06T11:50:28+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/7.pdf) |
| `moj-judgments-1434-volume-8.pdf` | مدونة أحكام | 3,518,655 | 386 | `d868ebfe6fc973b4adfc66f247af5f505cca6891fa73560b410c21049cfdcd2b` | `2026-09-06T11:50:35+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/8.pdf) |
| `moj-judgments-1434-volume-9.pdf` | مدونة أحكام | 3,696,508 | 433 | `a509db3eac4c6e5043bd1e587775ecc12c01e281056b276cdd6bca3275c8a9c1` | `2026-09-06T11:50:40+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/9.pdf) |
| `moj-judgments-1434-volume-10.pdf` | مدونة أحكام | 3,781,511 | 412 | `17172099759e4ae4a6305358e6d4d5bbec12444976069e1628e22ecb672ea010` | `2026-09-06T11:50:45+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/10.pdf) |
| `moj-judgments-1434-volume-12.pdf` | مدونة أحكام | 4,104,368 | 378 | `7fbbefdb8b810d9daac796f824690c44b591184def9ac255751a20224fa7afc8` | `2026-09-06T11:50:52+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/12.pdf) |
| `moj-judgments-1434-volume-14.pdf` | مدونة أحكام | 4,476,366 | 376 | `0faac966c633e1dad8ee3f8223fa401525eafdf75d2803e8d35e6c072becc830` | `2026-09-06T11:51:00+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/14.pdf) |
| `moj-judgments-1434-volume-15.pdf` | مدونة أحكام | 4,853,226 | 387 | `3e70236bdf469ad1869f69fe165b936b4af1b67d6540fa32c467ff95360207e8` | `2026-09-06T11:51:10+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/15.pdf) |
| `moj-judgments-1434-volume-16.pdf` | مدونة أحكام | 4,673,339 | 427 | `fbdf36deb24184bcd1453d4528d8e766d8800c753b8f21cfc3f22d9a916a242f` | `2026-09-06T11:51:16+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/16.pdf) |
| `moj-judgments-1434-volume-17.pdf` | مدونة أحكام | 3,563,724 | 512 | `0fd12ae23184b837d4064d9481aed000ccba83493f30c15f7c271684d9768d3d` | `2026-09-06T11:51:27+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/17.pdf) |
| `moj-judgments-1434-volume-18.pdf` | مدونة أحكام | 3,123,094 | 506 | `78873a7fe67123a392d1d8ed904a3d8a9a83abfe3e85f1b0d16961538d28f9da` | `2026-09-06T11:51:36+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/18.pdf) |
| `moj-judgments-1434-volume-19.pdf` | مدونة أحكام | 2,478,577 | 339 | `3b89f883e82d7873ba50f322388b29458eafbeb7548b6b06d6e5f32ce06c196e` | `2026-09-06T11:51:43+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/19.pdf) |
| `moj-judgments-1434-volume-20.pdf` | مدونة أحكام | 2,478,112 | 336 | `da777c85ad04c163536bc394d58196b0cd50748a8bfa960b0ac0ce725ed69659` | `2026-09-06T11:51:51+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/20.pdf) |
| `moj-judgments-1434-volume-21.pdf` | مدونة أحكام | 2,449,134 | 332 | `e583fce1668437c0845f2ce9c364757a6d048a0c1681c6fb2ec4cf870f8ae57d` | `2026-09-06T11:51:58+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/21.pdf) |
| `moj-judgments-1434-volume-22.pdf` | مدونة أحكام | 3,538,771 | 267 | `af23fd28ca115b52ffa13a98c2df44844943922b31cedde362a78702f8b9c133` | `2026-09-06T11:52:05+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/22.pdf) |
| `moj-judgments-1434-volume-23.pdf` | مدونة أحكام | 4,057,284 | 353 | `442bb453ae6df7ee553646855b1610c79bd7b97d72b72cb641762bc7da3dfa23` | `2026-09-06T11:52:15+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/23.pdf) |
| `moj-judgments-1434-volume-24.pdf` | مدونة أحكام | 8,366,296 | 369 | `9d0aa148f65f5c5468d29fb23ed346b56cdc0ad9e763d2404badbf750b51a03a` | `2026-09-06T11:52:22+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/24.pdf) |
| `moj-judgments-1434-volume-25.pdf` | مدونة أحكام | 4,701,062 | 420 | `f4e975329bbf9e33d2851c84b1de5273b52b9dc1c4fc9eda6d08f93f0b25aa9b` | `2026-09-06T11:52:30+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/25.pdf) |
| `moj-judgments-1434-volume-26.pdf` | مدونة أحكام | 2,868,672 | 375 | `b487906703f851e559d5d43a99eda6797f6b59d93f1b5d193e3f96e0bd45c27d` | `2026-09-06T11:52:41+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/26.pdf) |
| `moj-judgments-1434-volume-27.pdf` | مدونة أحكام | 4,269,148 | 317 | `432edec85c03e7879aec9a85cb09a8882ff47ee73e3462d17845190c68475efe` | `2026-09-06T11:52:51+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/27.pdf) |
| `moj-judgments-1434-volume-28.pdf` | مدونة أحكام | 4,354,201 | 309 | `427cfcd78c7d5368b2fbb4d9a63e685744daa9fd3ba2a58c586ded4a03e53de9` | `2026-09-06T11:52:59+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/28.pdf) |
| `moj-judgments-1434-volume-30.pdf` | فهرس مرجعي | 1,622,433 | 176 | `b61c94d5a3ac33d818c94a40b7744b666efee46d3cf62d31b87125745276724a` | `2026-09-06T11:53:10+00:00` | [وزارة العدل](https://www.moj.gov.sa/ar-sa/ministry/versions/Documents/backupFiles3/AhkamGroup_1434/30.pdf) |

الجهة المصدرة المسجلة لهذه الملفات هي **وزارة العدل السعودية**. يسجل ملف التدقيق الآلي اسم الأصل، والرابطين، والحجم، والبصمة، وتاريخ الاستلام، والجهة، وحالة القبول لكل رابط.

## السجلات والملفات المستقلة الجديدة حسب النوع

| النوع | سجلات جديدة | ملفات PDF مستقلة | ملاحظة |
|---|---:|---:|---|
| حكم | 981 | 981 | حدود الصفحات مأخوذة من الفهرس القائم وربطت بالأصل والبصمة والنطاق |
| صك | 0 | 0 | لم يُصنف أي ملف على أنه صك مستقل |
| تعميم | 0 | 0 | لم يظهر تعميم جديد قابل للتوثيق الثنائي |
| قرار | 0 | 0 | لم يظهر قرار جديد قابل للتوثيق الثنائي |
| مبدأ | 0 | 0 | لم يظهر أصل مبدأ جديد |
| سابقة | 0 | 0 | لم يظهر أصل سابقة جديد |
| مدونة/فهرس | 1 أصل فهرس مرجعي | 0 | الجزء 30 لعام 1434هـ محفوظ كفهرس ولم يُعامل كحكم |

لا تعني أرقام الصكوك أو القضايا الموجودة في بعض سجلات الأحكام أن هذه الملفات صُنفت كـ«صكوك» مستقلة؛ النوع القانوني للسجلات المضافة هو حكم فقط.

## الفشل والوصول المعلق

| الملف أو الرابط | الحالة | السبب أو الإجراء التالي |
|---|---|---|
| [https://www.bog.gov.sa/knowledge-center/JudicialBlogs/Pages/default.aspx](https://www.bog.gov.sa/knowledge-center/JudicialBlogs/Pages/default.aspx) | فشل النقل المباشر | `SSL_ERROR_SYSCALL`؛ كما أعاد متصفح السحابة `ERR_CONNECTION_CLOSED`. يلزم تنزيل رسمي من بيئة اتصال أخرى. |
| [https://www.bog.gov.sa/knowledge-center/JudicialBlogs/1444/Pages/default.aspx](https://www.bog.gov.sa/knowledge-center/JudicialBlogs/1444/Pages/default.aspx) | فشل النقل المباشر | `SSL_ERROR_SYSCALL`؛ كما أعاد متصفح السحابة `ERR_CONNECTION_CLOSED`. يلزم تنزيل رسمي من بيئة اتصال أخرى. |
| [https://www.bog.gov.sa/knowledge-center/PrinciplesBlogs/1439-1440-1441/Pages/default.aspx](https://www.bog.gov.sa/knowledge-center/PrinciplesBlogs/1439-1440-1441/Pages/default.aspx) | فشل النقل المباشر | `SSL_ERROR_SYSCALL`؛ كما أعاد متصفح السحابة `ERR_CONNECTION_CLOSED`. يلزم تنزيل رسمي من بيئة اتصال أخرى. |
| [https://www.bog.gov.sa/knowledge-center/JudicialBlogs/A1402-1436/Pages/default.aspx](https://www.bog.gov.sa/knowledge-center/JudicialBlogs/A1402-1436/Pages/default.aspx) | فشل النقل المباشر | `SSL_ERROR_SYSCALL`؛ كما أعاد متصفح السحابة `ERR_CONNECTION_CLOSED`. يلزم تنزيل رسمي من بيئة اتصال أخرى. |
| `https://t.me/robiai33` | تنزيل ثنائي معلق | المعاينة العامة بيانات وصفية فقط؛ يلزم اتصال Telegram مخول ثم SHA-256 والتحقق من المصدر الرسمي. |
| `moj-judgments-1434-volume-29.pdf` | تعارض بصمة قائم | السجل الرئيسي يعلن `d6c1…7465` بينما الملف المحفوظ يطابق السجل المعلق ببصمة `7eb1…de8c`. لم يُستبدل أي أصل أو إعلان مصدر. |

بعد الاسترداد بقي **11 أصلًا معلنًا غير موجود فعليًا**:

| الأصل المعلق |
|---|
| `banking-finance-principles.pdf` |
| `bog-administrative-precedents-1402-1436.pdf` |
| `commercial-contract-precedents.pdf` |
| `higher-judiciary-principles-1391-1437-runtime.pdf` |
| `higher-judiciary-principles-1391-1437.pdf` |
| `ip-judgments-1446.pdf` |
| `ip-precedents.pdf` |
| `judicial-precedents-compilation.pdf` |
| `judicial-precedents-study.pdf` |
| `nafa-judicial-library-1445.pdf` |
| `uncitral-arbitration-precedents-2024.pdf` |

## التكرارات والحالات المعلقة

لم تُكتشف بصمة ملف مستقلة مكررة أو بصمة نص صريحة مكررة ضمن السجلات الجديدة أو بينها وبين 1366 سجلًا قائمًا. لا توجد تكرارات مؤكدة في الدفعة الجديدة. ظهرت **7 صفوف تصادم مرجعي** ذات نصوص مختلفة، فبقيت في سجل مراجعة مستقل ولم تُدمج. كما كشف تدقيق العنوان عن **14 مجموعة** تضم 15 سجلًا زائدًا عن أول سجل؛ جميعها تحمل بصمات نص مختلفة، ولذلك سُجلت كمؤشر عنوان غير حاسم فقط.

احتُفظ أيضًا بحالة الجزء 29 لعام 1434هـ كسجل اختلاف اسم/بصمة مستقل؛ لم يُحذف أي أصل ولم تُستبدل أي نسخة متشابهة تلقائيًا.

## نتيجة التحقق النهائي

| اختبار التحقق | النتيجة | المقاييس |
|---|---|---|
| مدقق أرشيف الجامع القائم | ناجح | 1366 ملف حكم قائم، صفر أخطاء |
| مدقق دفعة الأصول المستردة | ناجح | 24 أصلًا، 981 سجلًا، 981 ملفًا مستقلًا، صفر معرفات أو بصمات صريحة مكررة |
| مدقق المخطط المستهدف | ناجح | 1758 وثيقة، 1419 ملف وثيقة، صفر أخطاء بصمة |
| مدقق NDJSON الخاص بالمهارة | ناجح | 2347 سجل حكم، صفر معرفات مكررة، صفر بصمات نص صريحة مكررة |
| صيغة JSON/NDJSON | ناجح | جميع الملفات غير الفارغة قابلة للتحليل؛ ملفا التدفق الفارغان مقبولان |
| مصالحة المصدر | ناجح مع حالات معلقة مسجلة | 45 صف تطابق، تعارض اسم/بصمة واحد، 11 أصلًا معلنًا مفقودًا |
| حواجز النشر | ناجح | صفر سجل مؤهل للبحث، صفر تنزيل عام، وصفر كتابة لقاعدة البيانات |

عالجت الدورة كذلك خلل خط الأساس في بيانات وصفية مشتقة: كانت بصمات 1366 سجل `document-files` قديمة، بينما ملفات PDF الفعلية وسجلات الجامع متطابقة. حُدّث حقل SHA-256 الوصفي فقط، مع سجل مصالحة قبل/بعد؛ لم تتغير هوية وثيقة أو نطاق صفحات أو حجم أو سياسة تنزيل أو ملف ثنائي، ولم تُكتب قاعدة البيانات.

## ما يحتاج إلى تدخل يدوي

يلزم مراجع قانوني التحقق من البيانات الوصفية للـ981 حكمًا قبل أي ترقية، وفحص حالات تصادم المرجع السبع ومجموعات تشابه العنوان الأربع عشرة، وحسم مصدر الجزء 29 لعام 1434هـ. يلزم كذلك تنزيل مخول لملفات Telegram، واتصال ناجح بمرفقات ديوان المظالم، واسترداد الأصول الإحدى عشرة المتبقية. لا يجوز تغيير أهلية البحث أو التنزيل قبل اكتمال هذه الخطوات.

## ملفات التدقيق الأساسية

- `manifests/audit/private-collector-cycle-20260906T1437+0300.json`
- `manifests/audit/moj-official-source-check-20260906T1450+0300.csv`
- `manifests/audit/bog-official-source-check-20260906T1453+0300.csv`
- `manifests/collector/recovered-validation-report.json`
- `manifests/audit/collector-full-ndjson-audit-20260906T1508+0300.json`
- `manifests/audit/moj-document-file-hash-reconciliation-20260906T1503+0300.ndjson`

سيظهر رابط الالتزام النهائي على `collector-import` في رسالة التسليم بعد الدفع. لا يوجد دمج إلى `main`.
