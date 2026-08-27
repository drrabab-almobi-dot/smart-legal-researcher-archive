# بوابة التجميع والفهرسة — Collector Portal

هذه الصفحة هي نقطة الدخول الموحدة لجميع أعمال التجميع والفهرسة على الفرع `collector-import`، بدون التأثير على `main`.

## الملفات الأصلية
- [أرشيف وزارة العدل 1434هـ](./archive-sources/moj/1434/)
- [أرشيف وزارة العدل 1435هـ](./archive-sources/moj/1435/)

## الفهارس والسجلات
- [فهرس الأحكام المستخرجة](./indices/collector/case-register.ndjson)
- [سجل ملفات الأحكام](./manifests/collector/judgment-file-register.csv)
- [سجل الاستيراد](./manifests/collector/import-log.csv)
- [سجل معالجة المصادر](./manifests/collector/processing-log.csv)
- [سجل المصادر المعلقة](./manifests/collector/pending-source-register.csv)
- [سجل التكرارات](./manifests/collector/pending-duplicates.csv)
- [عدد الأحكام حسب المصدر](./manifests/collector/source-case-counts.csv)
- [السجلات المتجاوزة](./manifests/collector/skipped-records.csv)

## ملفات التشخيص
- [تشخيص بنية المجلد الأول](./diagnostics/volume-1-structure-candidates.txt)
- [النص المستخرج من أول 80 صفحة](./diagnostics/volume-1-first-80-pages.txt)

## مهام التنفيذ
- [استيراد ملفات وزارة العدل](./.github/workflows/import-moj-judgments.yml)
- [فهرسة الأحكام المستخرجة](./.github/workflows/index-collector-judgments.yml)
- [الفهرسة وفق حدود الباحثة](./.github/workflows/index-collector-from-researcher-boundaries.yml)
- [فحص بنية المصدر](./.github/workflows/inspect-collector-source.yml)

## قاعدة العمل
كل حكم مستقل يجب أن يحفظ كملف PDF مستقل مع: عنوان القضية، رقم القضية، رقم الحكم/الصك، التاريخ، صفحات البداية والنهاية، عدد الصفحات، SHA-256، وربطه بالملف الأصلي. تتم المقارنة مع `main` لاحقًا، ولا يدمج إلا غير المكرر.
