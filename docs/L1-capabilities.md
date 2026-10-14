# Autonomous Career Opportunity Agent (ACOA)
## L1 — Ana Yetenekler ve Sistem Genelindeki Mühendislik Gereksinimleri

| Alan | Değer |
|---|---|
| Belge kodu | ACOA-L1 |
| Belge seviyesi | L1 — Yetenek ve kalite alanları |
| Sürüm | 0.1 — İlk kapsamlı taslak |
| Durum | L1 kapsamı kullanıcı tarafından onaylandı |
| Üst belge | `Autonomous_Career_Opportunity_Agent_Project_Definition.md` (L0) |
| Amaç | L0 vizyonunu, L2'de ayrıştırılabilecek, sınırları belirli ve izlenebilir sistem yeteneklerine dönüştürmek |

> **Temel kural:** Bu belge sistemin **neler yapması gerektiğini** ve **hangi mühendislik niteliklerini taşıması gerektiğini** tanımlar. Belirli araçları, modelleri, agent sayılarını, klasör yapısını veya altyapıyı seçmez. Bunlar L2 gereksinimleri netleşince L3 tasarımında kararlaştırılır.

---

# 1. Yaklaşım ve kavramlar

## 1.1. L1'in rolü

L0: Neyi ve neden geliştiriyoruz?  
**L1: Hangi yetenekler ve sistem genelindeki nitelikler zorunlu?**  
L2: Her yeteneğin alt işlevleri, kuralları, veri ve durum gereksinimleri nedir?  
L3: Bunların teknik tasarımı ve uygulama stratejisi nedir?  
L4: Kod, test, ölçüm ve kabul nasıl sağlanacak?

L1'de tanımlanan bir *yetenek*, tek bir yazılım modülü, bağımsız servis ya da AI agent'ı anlamına gelmez. Bir yetenek deterministik kod, kural motoru, model çağrısı veya bunların birleşimiyle uygulanabilir. Nihai agent sayısı ve AI modeli sayısı bu belgede belirlenmez.

## 1.2. Terimler

- **Opportunity (Fırsat):** Bir kurumla ücretli veya diğer meşru profesyonel çalışma ilişkisi kurma ihtimali. Yayımlanmış bir ilan ya da açıkça *potansiyel ve doğrulanmamış* olarak işaretlenen ilan dışı fırsat olabilir.
- **Lead (Aday kurum/temas):** Henüz doğrulanmış açık bir iş imkânı olmayan, araştırılmaya değer kurum veya resmî iletişim kanalı.
- **Application (Başvuru):** Kullanıcı adına, belirlenmiş bir profesyonel fırsata yönelik resmî başvuru veya uygun biçimde iletilmiş adaylık girişimi.
- **Submission evidence (Gönderim kanıtı):** Form onayı, gönderilmiş e-posta kaydı veya karşı taraftan gelen teyit gibi işlemin gerçekleşme durumunu destekleyen kayıt.
- **Autonomy policy (Otonomi politikası):** Hangi işlemlerin otomatik, hangilerinin onayla, hangilerinin hiçbir koşulda yapılmayacağını belirleyen yetki sınırı.
- **Capability (Yetenek):** Ne yapılması gerektiğini tanımlayan mantıksal sorumluluk alanı; agent veya kod modülü değildir.
- **Quality requirement (Kalite/mühendislik gereksinimi):** Bütün yeteneklerin nasıl bir güvenlik, güvenilirlik, kalite ve verimlilikle çalışacağını tanımlayan çapraz kesen yükümlülük.

## 1.3. L1 sınıflandırması

Bu belge iki eksen kullanır:

- **F — Functional Capabilities:** Sistemin dışarıdan gözlemlenebilen iş ve kullanıcı görevleri.
- **E — Engineering Capabilities:** Bütün bu görevlerin güvenilir, güvenli, ölçülebilir, ekonomik ve sürdürülebilir çalışması için sistem genelindeki yükümlülükler.

Kimlikler `F-01…F-12` ve `E-01…E-12` biçimindedir. L1 başlıklarının her biri L2'de numaralı, test edilebilir gereksinimlere dönüşecektir. Öncelik ve sürüm kapsamı henüz karara bağlanmamıştır.

---

# 2. L1 yetenek haritası

## 2.1. Fonksiyonel yetenekler

| Kimlik | Alan | Birincil sorumluluk |
|---|---|---|
| **F-01** | Kullanıcı Profili ve Hedef Yönetimi | Kullanıcının doğrulanmış mesleki kimliğini, hedeflerini, tercihlerini ve kısıtlarını temsil etmek |
| **F-02** | Kaynak ve Kurum Keşfi | Farklı açık ve yetkili kaynaklardan araştırılacak şirketleri ve kaynakları bulmak |
| **F-03** | Fırsat Tespiti ve Normalizasyonu | İlanları ve ilan dışı potansiyel fırsatları tanımlamak, ayrıştırmak ve kayda geçirmek |
| **F-04** | Şirket ve İletişim Araştırması | Kurumu, çalışma bağlamını ve uygun resmî temas kanallarını incelemek |
| **F-05** | Uygunluk ve Öncelik Analizi | Fırsatları kullanıcı hedeflerine göre değerlendirmek ve sıralamak |
| **F-06** | Başvuru ve Erişim Stratejisi | Bir fırsata hangi izinli kanal ve yöntemlerle yaklaşılacağını belirlemek |
| **F-07** | Başvuru İçeriği ve Belge Hazırlama | Doğru, izlenebilir ve kişiselleştirilmiş başvuru materyalleri üretmek |
| **F-08** | Dijital Etkileşim ve İşlem Gerçekleştirme | Yetkili web, form, e-posta ve diğer kanallarda gerçek işlemleri yürütmek |
| **F-09** | İletişim ve Takip Yönetimi | Yazışmaları ilişkilendirmek, yanıtları yorumlamak, takip adımlarını planlamak |
| **F-10** | Başvuru ve Fırsat Yaşam Döngüsü | Fırsat, başvuru, temas ve sonuç durumlarını tutarlı biçimde takip etmek |
| **F-11** | Proaktif ve Sürekli Çalışma | Sistem görevlerini belirlenen düzende devam ettirmek ve gelişmeleri yeniden değerlendirmek |
| **F-12** | Kullanıcı Kontrolü ve Geri Bildirim | Hedef, yetki, faaliyet, onay, durdurma ve düzeltme işlemlerini kullanıcının yönetebilmesi |

## 2.2. Mühendislik ve kalite alanları

| Kimlik | Alan | Birincil sorumluluk |
|---|---|---|
| **E-01** | Uyarlanabilir Zekâ ve Model Yönlendirme | Görev için gerekli AI düzeyini ve yöntemini seçmek |
| **E-02** | Token, Maliyet ve Kaynak Optimizasyonu | Kaliteyi koruyarak toplam işlem maliyetini kontrol etmek |
| **E-03** | Görev Planlama ve Orkestrasyon | Görevleri bağımlılıklarıyla yönetmek, koordine etmek ve durdurmak |
| **E-04** | Güvenilirlik ve İşlem Bütünlüğü | Hataları, kesintileri, belirsiz gönderimleri ve tekrarları güvenle yönetmek |
| **E-05** | Hafıza, Durum, Veri ve Bağlam Yönetimi | Doğru bilgiyi doğru biçimde saklamak, sürdürmek ve ilgili görevlerde kullanmak |
| **E-06** | Kanıt, Doğrulama ve Karar Kalitesi | Kaynağı, güveni, belirsizliği ve karar gerekçesini yönetmek |
| **E-07** | Güvenlik, Yetkilendirme ve Uyumluluk | Kimlik, izinler, kişisel veriler, iletişim ve dış sistem sınırlarını korumak |
| **E-08** | Gözlemlenebilirlik ve Denetlenebilirlik | Olayların, kararların, maliyetlerin ve sonuçların izini tutmak |
| **E-09** | Test, Değerlendirme ve Kontrollü İyileştirme | Davranış kalitesini sistematik olarak ölçmek ve regresyonu önlemek |
| **E-10** | Modülerlik, Genişletilebilirlik ve Bakım | Sağlam arayüzlerle teknoloji bağımlılığını ve gereksiz karmaşıklığı azaltmak |
| **E-11** | Performans, Ölçeklenebilirlik ve İşletim | İş hacmi ve kesintiler karşısında öngörülebilir çalışma sağlamak |
| **E-12** | Hedef ve Sonuç Optimizasyonu | İşlem adedi yerine nitelikli profesyonel sonuçları optimize etmek |

---

# 3. Fonksiyonel yeteneklerin L1 tanımları

## F-01 — Kullanıcı Profili ve Hedef Yönetimi

**Amaç:** Kullanıcının doğrulanmış kimliğini, mesleki geçmişini ve fırsat tercihlerini kararların güvenilir referansı hâline getirmek.

**Sorumluluklar:** Mesleki deneyim, yetkinlikler, eğitim, dil, konum/çalışma biçimi tercihleri, hedef roller, ücret ve diğer tercih/kısıtları temsil etmek; hangi bilginin kullanıcı tarafından doğrulandığını ayırt etmek; birden fazla profil veya CV versiyonunu ihtiyaç halinde ilişkilendirmek; değişikliklerin sonraki kararları nasıl etkilediğini göstermek.

**Girdi → Çıktı:** Kullanıcı beyanları ve yetkili belgeler → doğrulanmış profil, hedef/kısıt seti ve kaynak bağlantıları.

**Sınır:** Profil bilgilerini kendiliğinden uydurmaz; yetki uygulanmasını bu alan tek başına yapmaz (E-07); belge üretimini F-07 yapar.

**Başarı işareti:** Farklı süreçler aynı güncel ve doğrulanabilir kullanıcı bilgileriyle çalışır.

## F-02 — Kaynak ve Kurum Keşfi

**Amaç:** Tek bir iş ilanı platformuna bağlı olmadan araştırılmaya değer kaynakları, kurumları ve potansiyel işverenleri bulmak.

**Sorumluluklar:** Genel web, kurumsal siteler, kariyer portalları ve izinli açık kaynakları tarayabilecek stratejileri desteklemek; kaynakların kapsama alanını yönetmek; yeni kurumları ve değişiklikleri keşfetmek; tekrarları ve kullanılamayan kaynakları ayırt etmek.

**Girdi → Çıktı:** Kullanıcı hedefleri, arama kriterleri, önceki keşif kayıtları → kaynak/kandidat kurum listesi ve keşif kanıtları.

**Sınır:** Bulunan kurumun gerçekten açık pozisyonu bulunduğunu varsaymaz (F-03); özel verilere izinsiz erişmez (E-07).

**Başarı işareti:** Aynı hedef için alternatif kaynaklar araştırılabilir ve keşif kaynağı izlenebilir.

## F-03 — Fırsat Tespiti ve Normalizasyonu

**Amaç:** Dağınık kaynaklardan elde edilen sinyalleri tutarlı, karşılaştırılabilir fırsat kayıtlarına dönüştürmek.

**Sorumluluklar:** Açık iş ilanlarını ve ilan dışı potansiyel çalışma fırsatlarını ayrı türler olarak ele almak; şirket, rol, konum, çalışma biçimi, ilan durumu, son tarih ve kaynak gibi alanları elde etmek; kaynaklar arasında aynı fırsatı eşleştirmek; güncellik ve belirsizlik bilgisini korumak.

**Girdi → Çıktı:** Keşif sonuçları, sayfa veya kaynak içeriği → normalize edilmiş ilan/fırsat kaydı ve kanıt bağlantısı.

**Sınır:** İlan bulunmayan şirketi 'kesin işe alıyor' biçiminde sunmaz; uygunluk puanı üretmek F-05'in görevidir.

**Başarı işareti:** Aynı ilan birden fazla kanalda görüldüğünde tekilleştirilir; varsayım ve doğrulanmış durum karıştırılmaz.

## F-04 — Şirket ve İletişim Araştırması

**Amaç:** Potansiyel işverenin bağlamını ve başvuru için meşru, uygun temas yollarını belirlemek.

**Sorumluluklar:** Şirketin faaliyet alanı, ürünleri, işe alım kanalları ve gerektiğinde ilgili ekiplerini araştırmak; resmî kariyer/iletişim sayfaları ile kamuya açık kurumsal temas bilgilerini saptamak; kanalların geçerliliğini ve kaynağını değerlendirmek.

**Girdi → Çıktı:** Kurum/fırsat kimliği, açık kurumsal bilgiler → kurum profili ve kanıtlı iletişim kanalları.

**Sınır:** Kişilerin özel iletişim bilgilerini izinsiz toplamaz; gerçek olmayan adresler uydurmaz; kurum araştırması başvuru gönderimi değildir.

**Başarı işareti:** Hangi iletişim kanalının neden uygun görüldüğü açıklanabilir.

## F-05 — Uygunluk ve Öncelik Analizi

**Amaç:** Değeri yüksek, kullanıcının hedeflerine uygun fırsatları önceliklendirmek.

**Sorumluluklar:** Zorunlu kısıtları kontrol etmek; beceri/deneyim uyumu, fırsat kalitesi, kullanıcı tercihleri, belirsizlik ve başvuru maliyetini değerlendirmek; uygun, düşük öncelikli, belirsiz veya hariç sonuçlarını gerekçelendirmek; yanlış eleme riskini dikkate almak.

**Girdi → Çıktı:** Profil, fırsat kaydı ve araştırma kanıtları → gerekçeli uygunluk/öncelik kararı.

**Sınır:** Eksik veri olduğunda kesin kanaat üretmez; başvuru kanalı seçimi F-06'dadır.

**Başarı işareti:** Öncelik kararları kullanıcı hedefleriyle tutarlıdır ve incelenebilir.

## F-06 — Başvuru ve Erişim Stratejisi

**Amaç:** Belirli bir fırsat veya potansiyel işveren için en uygun, izinli ve ölçülü erişim yolunu seçmek.

**Sorumluluklar:** Resmî başvuru, kariyer sayfası, kurumsal e-posta, uygun iletişim formu veya bekleme/izleme seçeneklerini karşılaştırmak; ilk girişim ile takip girişimini ayırmak; uygulanamayan veya uygunsuz kanallarda alternatif belirlemek; işlem planı ve gerekçesini üretmek.

**Girdi → Çıktı:** Uygunluk kararı, kurum/kanal araştırması, yetki ve iletişim kısıtları → gerekçeli erişim planı.

**Sınır:** Bu alan planı üretir, dış dünyada gönderim yapmaz (F-08). Sayısal gönderim limitleri, izin ve yasaklar E-07 tarafından uygulanır.

**Başarı işareti:** Kullanılabilir birden fazla kanal varsa tercih nedeni açıktır; uygun kanal yoksa işlem yapılmaz.

## F-07 — Başvuru İçeriği ve Belge Hazırlama

**Amaç:** Her başvuru için uygun, kişiselleştirilmiş ve doğru belge/iletişim materyali oluşturmak.

**Sorumluluklar:** Doğrulanmış profilden CV, ön yazı, tanıtım e-postası, başvuru yanıtları ve gerekirse ilgili diğer profesyonel materyalleri üretmek; içeriği şirket/rol bağlamına uyarlamak; kaynak bilgisini ve versiyonlarını saklamak; ifade/format kalitesini kontrol etmek.

**Girdi → Çıktı:** Doğrulanmış profil, fırsat ve strateji → başvuruya hazır içerik ve belge versiyonları.

**Sınır:** Deneyim, sertifika, başarı, unvan ve tarih uydurmaz; üretilen taslak otomatik olarak gönderilmiş sayılmaz.

**Başarı işareti:** Her önemli kişisel iddia kaynak profille tutarlıdır; gönderilen belge versiyonu bilinir.

## F-08 — Dijital Etkileşim ve İşlem Gerçekleştirme

**Amaç:** Onaylanmış strateji ve yetki dahilinde dış sistemlerde gerçek işlemler gerçekleştirmek.

**Sorumluluklar:** Uygun olduğunda API, web sayfası, form, e-posta veya diğer izinli kanalları kullanmak; form doldurma, dosya yükleme, gönderim ve doğrulama adımlarını yönetmek; işlemin başlatılmasıyla gerçekten tamamlanmasını ayırmak; başarısız veya doğrulanamayan gönderimleri raporlamak.

**Girdi → Çıktı:** Eylem planı, yetki kararı, hazırlanmış materyal → işlemin sonucu ve gönderim kanıtı/sonuç belirsizliği.

**Sınır:** Her siteyi aşabileceği varsayılmaz; CAPTCHA, oturum ve erişim kısıtlarını hukuka veya hizmet koşullarına aykırı biçimde aşmaz; tekrar gönderme kararı E-04 kontrolüne tabidir.

**Başarı işareti:** Başvuru *hazırlandı*, *gönderim denendi*, *gönderildiği doğrulandı* ve *sonuç belirsiz* durumları ayrıdır.

## F-09 — İletişim ve Takip Yönetimi

**Amaç:** Başvuru sonrasındaki veya ilan dışı erişim girişimindeki iletişimi bağlamını koruyarak yönetmek.

**Sorumluluklar:** Gelen ve giden iletişimi doğru şirket/fırsat ile ilişkilendirmek; yanıtları sınıflandırmak; görüşme isteği, ek belge talebi, ret, yanıtsızlık ve iletişimden çıkma taleplerini ayırt etmek; uygun takip eylemlerini önermek veya yetki dahilinde başlatmak.

**Girdi → Çıktı:** Mesajlar, başvuru geçmişi, iletişim politikası → konuşma durumu ve takip görevi/yanıt stratejisi.

**Sınır:** Mesajların fiziksel gönderimi F-08 üzerinden yapılır; kullanıcı adına bağlayıcı anlaşma veya ücret kabulü izinsiz yapılmaz; iletişimden çıkma talepleri esas alınır.

**Başarı işareti:** Her takip girişimi geçmiş konuşmaya bağlıdır; tekrar ve uygunsuz ısrar engellenir.

## F-10 — Başvuru ve Fırsat Yaşam Döngüsü

**Amaç:** Keşiften kapanışa kadar fırsat ve başvuruların iş durumunu tek bir güvenilir görünümde korumak.

**Sorumluluklar:** Fırsatların, şirketlerin, hazırlanmış materyallerin, gönderimlerin, yazışmaların ve kararların ilişkisini tutmak; açık/kapalı/beklemede gibi iş durumlarını kaydetmek; tekrar girişimleri fark etmek; sonuçları ve sonraki eylemleri kullanıcıya sunmak.

**Girdi → Çıktı:** Diğer F alanlarından gelen doğrulanmış olaylar → güncel başvuru hattı ve iş geçmişi.

**Sınır:** Teknik veri saklama yöntemi E-05'in ve L3'ün konusudur; dış sisteme yapılmamış işlemi 'gönderildi' olarak kaydetmez.

**Başarı işareti:** Tek bir başvuru için hangi eylemin ne zaman ve ne kanıtla yapıldığı anlaşılır.

## F-11 — Proaktif ve Sürekli Çalışma

**Amaç:** Tek seferlik talimatların ötesinde, kullanıcının belirlediği çalışma düzeninde fırsat ve başvuru süreçlerini sürdürmek.

**Sorumluluklar:** Tanımlı dönemlerde araştırmayı yenilemek; değişen ilan, şirket ve iletişim durumlarına tepki vermek; ertelenmiş takipleri yeniden değerlendirmek; gereksiz tekrarı ve bitmeyen araştırma döngülerini önlemek; yeni görevlerin önceliklerini yeniden belirlemek.

**Girdi → Çıktı:** Hedefler, takvim/izleme tercihleri, mevcut durum → yeni ya da yeniden planlanan görevler.

**Sınır:** Zamanlayıcı/dağıtım teknolojisi L3'te seçilir; sürekli çalışma sınırsız API tüketimi veya sınırsız mesaj gönderimi demek değildir.

**Başarı işareti:** Sistem kesintisiz insan yönetimi gerektirmeden uygun işler başlatır; durdurma/limit politikalarına uyar.

## F-12 — Kullanıcı Kontrolü ve Geri Bildirim

**Amaç:** Kullanıcının amaç, yetki ve temsil üzerinde sürekli gerçek kontrol sahibi olmasını sağlamak.

**Sorumluluklar:** Hedef/tercih değiştirme, otomatik işlem yetkilerini yönetme, seçili işlemleri inceleme/onaylama, sistemi duraklatma, dışlama listeleri düzenleme, yanlış verileri düzeltme ve geri bildirim verme imkânı sunmak; işleyişi anlaşılır biçimde göstermek.

**Girdi → Çıktı:** Kullanıcı komutları, geri bildirim ve onaylar → güncellenmiş hedefler, yetkiler, durdurmalar ve düzeltme kayıtları.

**Sınır:** Kontrol yüzeyinin web paneli, CLI veya başka arayüz olup olmayacağı L3 kararına bırakılır; F-12 politika uygulamasının tek güvenlik katmanı değildir (E-07).

**Başarı işareti:** Kullanıcı planlanan ve tamamlanan kritik dış eylemleri görebilir, yetkileri geri çekebilir ve faaliyetleri durdurabilir.

---

# 4. Sistem genelindeki mühendislik gereksinimleri

Bu alanlar **F-01'den F-12'ye kadar bütün fonksiyonel yetenekleri gerektiği ölçüde keser**. Bir kategorinin listede olması ayrı bir LLM agent'ı veya servis oluşturma zorunluluğu doğurmaz.

## E-01 — Uyarlanabilir Zekâ ve Model Yönlendirme

**Amaç:** Görevin niteliğine göre en uygun karar mekanizmasını kullanmak.

**Gereksinim:** Sistem önce deterministik yöntemlerin yeterli olup olmadığını değerlendirmeli; AI gerektiğinde model yeteneğini, akıl yürütme derinliğini, görev karmaşıklığını, belirsizliği ve işlem riskini birlikte göz önünde bulundurmalıdır. Yetersiz kalite veya belirsizlik durumunda daha yetkin yöntemlere kontrollü yükseltme ve gerektiğinde insana devretme sağlayabilmelidir.

**Sınır:** Her yetenek için sabit model seçimi veya her alt iş için yeni agent zorunluluğu yoktur. Yanıtın maliyeti tek başına seçim kriteri değildir.

**Ölçüm örnekleri:** Görev sınıfı bazında doğruluk; yeniden deneme ve yükseltme oranı; farklı yönlendirme politikalarının kalite-maliyet farkı.

## E-02 — Token, Maliyet ve Kaynak Optimizasyonu

**Amaç:** Kabul edilen kalite ve güvenlik düzeyinde nitelikli sonuca ulaşmanın toplam maliyetini azaltmak.

**Gereksinim:** Model çağrısı, token, arama, tarayıcı, altyapı, zaman ve iletişim maliyetleri ölçülebilmeli; görev ve dönem bazında bütçeler tanımlanabilmeli; tekrar kullanılan bilgiler için önbellek, gereksiz işlerin erken sonlandırılması, uygun gruplama ve bağlam azaltma gibi teknikler değerlendirilebilmelidir.

**Sınır:** En düşük token tüketimi uğruna kritik doğruluk ve güvenlik denetimleri kaldırılamaz. Bütçe kısıtı aşıldığında sistem politika doğrultusunda durmalı, ertelemeli veya kullanıcıya bildirmelidir.

**Ölçüm örnekleri:** Nitelikli fırsat/başvuru başına maliyet; model çağrısı başına harcama; boşa giden tekrar oranı.

## E-03 — Görev Planlama ve Orkestrasyon

**Amaç:** Birden fazla adımdan oluşan hedefleri bağımlılıkları ve sınırlarıyla yönetmek.

**Gereksinim:** Görevler ayrıştırılabilmeli, önceliklendirilebilmeli, bağımlılıklar belirlenebilmeli, paralel veya sıralı işletilebilmeli, gerektiğinde yeniden planlanabilmeli ve sonlandırılabilmelidir. Planın ilerleme ve tamamlanma koşulları açık olmalıdır.

**Sınır:** Orkestrasyon yapısı tek-agent, çoklu-agent veya karma iş akışı olabilir; topoloji L3'te gerekçelendirilecektir.

**Ölçüm örnekleri:** Başarıyla tamamlanan uçtan uca iş oranı; gereksiz adım sayısı; kilitlenme/sonsuz döngü sayısı.

## E-04 — Güvenilirlik ve İşlem Bütünlüğü

**Amaç:** Kesintilere, yanlış tekrar denemelere ve belirsiz dış işlem sonuçlarına rağmen tutarlı davranmak.

**Gereksinim:** İşlemlerin teknik ve iş durumları ayrılmalı; geçici/kalıcı hatalar sınıflandırılmalı; zaman aşımı, tekrar deneme, kontrollü durdurma, yeniden başlatma ve kurtarma senaryoları desteklenmelidir. Gerçek dünyada yan etki yaratan işlemler tekrarlanmadan önce önceki sonuç araştırılmalıdır.

**Sınır:** Her dış platform tam olarak bir kez gönderim garantisi sağlamaz. Sistem, garanti edemediği sonucu kesinmiş gibi sunmak yerine belirsizliği korumalıdır.

**Ölçüm örnekleri:** Yinelenen başvuru; doğrulanmamış gönderimin yanlış başarılı işaretlenmesi; kesinti sonrası kurtarılabilen görevler.

## E-05 — Hafıza, Durum, Veri ve Bağlam Yönetimi

**Amaç:** Gerektiğinde geçmişten yararlanırken yanlış, eski veya gereksiz bilgiyi kullanmamak.

**Gereksinim:** Doğrulanmış kullanıcı gerçekleri, harici kaynak bulguları, operasyonel durum ve geçici görev bağlamı birbirinden ayrılmalıdır. Bilgilerin kaynak, zaman, sürüm ve güncellik nitelikleri korunmalı; her göreve yalnızca gerekli ve yetkili bağlam sağlanmalıdır.

**Sınır:** Uzun bağlam veya tüm geçmişin modele verilmesi 'iyi hafıza' anlamına gelmez. Teknik depolama çözümü L3'te seçilir.

**Ölçüm örnekleri:** Eski bilgi kullanımına dayalı hata; gereksiz bağlam token oranı; çelişkili kayıt sıklığı.

## E-06 — Kanıt, Doğrulama ve Karar Kalitesi

**Amaç:** Web'de karşılaşılan iddiaları, ihtimalleri ve doğrulanmış sonuçları birbirine karıştırmamak.

**Gereksinim:** Önemli araştırma bulgularının kaynağı ve zaman bilgisi tutulmalı; belirsizlik ve kaynak güvenilirliği belirtilmeli; kritik kararlar denetlenebilir gerekçelerle desteklenmelidir. Şirket, pozisyon, iletişim bilgisi ve başvuru sonucuna ilişkin iddialarda uydurma içerik önlenmelidir.

**Sınır:** LLM'nin kendine verdiği güven puanı tek başına gerçek doğrulama sayılmaz.

**Ölçüm örnekleri:** Doğrulanamayan kritik iddia sayısı; yanlış fırsat/iletişim tespiti; karar gerekçesi kapsaması.

## E-07 — Güvenlik, Yetkilendirme ve Uyumluluk

**Amaç:** Kullanıcıyı, kimlik bilgilerini ve üçüncü kişileri korurken sistemin izinli biçimde işlem yapmasını sağlamak.

**Gereksinim:** Dış işlemler için açık yetki kapsamı, izin düzeyi, durdurma/geri çekme, veri minimizasyonu ve güvenli kimlik bilgisi yönetimi bulunmalıdır. Harici sayfa ve mesajlar güvenilmeyen veri olarak ele alınmalı; prompt injection ve yetki aşımı engellenmelidir. Kurumsal iletişim, gizlilik ve hizmet koşullarına uygunluk kontrol edilmeli; rahatsız edici veya izinsiz kitlesel gönderim engellenmelidir.

**Sınır:** CAPTCHA veya giriş korumasını yetkisiz aşmak, sahte beyan, kişisel veri sızdırma ve kullanıcının onaylamadığı bağlayıcı taahhütler kapsam dışıdır.

**Ölçüm örnekleri:** Yetkisiz dış işlem; gizli veri açığı; iletişimden çıkma taleplerine uyumsuzluk; güvenlik testi başarısı.

## E-08 — Gözlemlenebilirlik ve Denetlenebilirlik

**Amaç:** Sistemin ne yaptığını, neden yaptığını ve sonucu nasıl bildiğini yeniden inceleyebilmek.

**Gereksinim:** Önemli görevler için başlatma/bitiş, karar, kullanılan kaynak ve yöntem, harcama, hata, yetki kontrolü ve sonuç kanıtları ilişkilendirilebilir olmalıdır. Kullanıcı ve geliştirici için gerekli görünürlük sağlanmalı; hassas veriler günlüklerde açık biçimde tutulmamalıdır.

**Sınır:** Tüm iç model düşüncelerini saklamak şart değildir; denetlenebilir işlem özeti, girdiler/çıktılar ve gerekçeler yeterlilik ölçütüdür.

**Ölçüm örnekleri:** İzlenebilir işlem yüzdesi; teşhis süresi; eksik kanıt/olay sayısı.

## E-09 — Test, Değerlendirme ve Kontrollü İyileştirme

**Amaç:** Değişikliklerin gerçekten fayda sağlayıp sağlamadığını ölçmek ve mevcut işlevselliği korumak.

**Gereksinim:** Deterministik birim testleri, dış sistem taklitleri, görev senaryoları, gerçek dünyaya yakın değerlendirme setleri ve kontrollü karşılaştırmalar desteklenmelidir. Başvuru gönderme ve mesaj yollama gibi yan etkili işler için güvenli simülasyon veya deneme modu bulunmalıdır. Model değişiklikleri kalite ve maliyet açısından karşılaştırılmalıdır.

**Sınır:** Sadece modelin cevabının 'mantıklı görünmesi' kabul testi değildir.

**Ölçüm örnekleri:** Senaryo geçiş oranı; regresyon sayısı; insan incelemesinde tespit edilen kritik hata oranı.

## E-10 — Modülerlik, Genişletilebilirlik ve Bakım

**Amaç:** Sistem bileşenlerinin anlaşılabilir, değiştirilebilir ve bağımsız sınanabilir olmasını sağlamak.

**Gereksinim:** Sorumluluklar açık sınırlara ayrılmalı; veri/araç/model sağlayıcı bağımlılıkları soyut ve test edilebilir arayüzler üzerinden yönetilebilmeli; tekrar eden mantık ortaklaştırılmalı; ancak gereksiz soyutlama ve agent enflasyonu önlenmelidir. Mimari kararlar gerekçeleriyle kayıt altına alınmalıdır.

**Sınır:** Mikroservis, çoklu agent veya belirli tasarım kalıbı zorunlu değildir.

**Ölçüm örnekleri:** Bir araç/model değişiminden etkilenen alanlar; değişiklik maliyeti; bağımsız test edilebilirlik.

## E-11 — Performans, Ölçeklenebilirlik ve İşletim

**Amaç:** Sistemin kaynak ve dış servis sınırları altında öngörülebilir biçimde çalışmasını sağlamak.

**Gereksinim:** Eşzamanlılık, hız limitleri, kuyruklama, yük altında davranış, zaman aşımı, geri basınç (backpressure), geçici bağlantı hataları, başlangıç/kapanış ve iş sürekliliği gereksinimleri belirlenebilmelidir. Görevlerin kaynak tüketimi ve darboğazları izlenebilir olmalıdır.

**Sınır:** İlk sürümden yüksek ölçekli dağıtık altyapı beklenmez. Performans hedefleri ve kapasite eşikleri L2'de somutlaştırılır.

**Ölçüm örnekleri:** İşlem süresi; tıkanan görev oranı; dış servis limitine uyum; kaynak kullanımı.

## E-12 — Hedef ve Sonuç Optimizasyonu

**Amaç:** Agent'ın çok işlem yapmak yerine kullanıcı için faydalı profesyonel sonuçlar üretmeye yönelmesini sağlamak.

**Gereksinim:** Nitelikli fırsat, doğrulanmış başvuru, olumlu yanıt, görüşme ve diğer hedef ilerleme göstergeleri tanımlanabilmeli; faaliyet yoğunluğu ile gerçek sonuç kalitesi ayrı ölçülmelidir. Sistem sonuçlardan yararlanarak arama, önceliklendirme ve iletişim stratejilerini kontrollü biçimde uyarlayabilmelidir.

**Sınır:** Çok fazla e-posta veya başvuru göndermek tek başına başarı değildir; optimizasyon dürüstlük, güvenlik ve kullanıcı tercihlerini aşamaz.

**Ölçüm örnekleri:** Nitelikli başvuru başına toplam maliyet; uygun fırsat oranı; olumlu dönüş/görüşme oranı; kullanıcı memnuniyeti.

---

# 5. Alanlar arası zorunlu sistem sözleşmeleri

Aşağıdaki ilkeler belirli bir fonksiyona devredilerek ortadan kaldırılamaz; sistemin bütünü tarafından korunmalıdır.

| Kod | Sistem sözleşmesi | Etkilenen başlıca alanlar |
|---|---|---|
| **X-01** | Dış tarafa mesaj, CV veya başvuru gönderimi **geçerli bir yetki politikasından** geçmeden gerçekleşmez. | F-06, F-07, F-08, F-09, F-12, E-07 |
| **X-02** | Kullanıcı hakkında üretilen her önemli kişisel iddia, doğrulanmış profil ile tutarlı olmalıdır. | F-01, F-07, E-05, E-06 |
| **X-03** | Bir işlemin *planlanması*, *denenmesi*, *gerçekleşmesi* ve *kanıtlanması* farklı durumlardır. | F-08, F-10, E-04, E-08 |
| **X-04** | Gönderim sonucu belirsizse aynı eylem kontrolsüz şekilde tekrarlanmaz. | F-08, F-09, F-10, E-04 |
| **X-05** | Kaynağı doğrulanmamış şirket, ilan veya iletişim bilgisi kesin olarak sunulmaz. | F-02, F-03, F-04, F-05, E-06 |
| **X-06** | Araç veya model seçimi, kalite ve risk eşiği sağlanarak toplam kaynak verimliliğini gözetir. | Bütün F alanları; E-01, E-02, E-12 |
| **X-07** | Web sayfalarının ve gelen e-postaların içeriği **komut yetkisine sahip değildir**. | F-02, F-04, F-08, F-09, E-07 |
| **X-08** | Kullanıcı duraklatma, hariç tutma ve yetki iptalini tüm ilgili eylemlere uygulatabilir. | F-11, F-12, E-03, E-07 |
| **X-09** | İletişim sıklığı, geçerli kurallar ve karşı tarafın iletişimden çıkma isteği gözetilir. | F-06, F-08, F-09, E-07, E-12 |
| **X-10** | Kritik olaylar, veri gizliliğini koruyarak incelenebilir kayıtlara bağlanır. | F-08, F-10, E-05, E-08 |

---

# 6. Uçtan uca örnek davranışlar (L1 seviyesinde)

Bunlar sıralı zorunlu yazılım akışları değil; alanlar arası işbirliğini anlatan senaryolardır. Her aşama, ilgili mühendislik yükümlülükleriyle korunur.

## Senaryo A — Yayımlanmış iş ilanı

1. **F-01** kullanıcının hedeflerini ve doğrulanmış profilini sağlar.
2. **F-02/F-03** kaynaklarda bir ilan keşfeder, kaydeder ve tekilleştirir.
3. **F-04/F-05** şirketi araştırır, kullanıcıya uygunluğu değerlendirir.
4. **F-06** izinli başvuru yöntemini ve adımlarını belirler.
5. **F-07** doğru CV ve gerekli materyalleri hazırlar.
6. **E-07** yetki/iletişim kısıtlarını denetler; **F-08** uygun yöntemle başvurur.
7. **E-04/E-06** gönderim sonucunun doğrulanma düzeyini belirler; **F-10** kaydeder.
8. **F-09/F-11** yanıtları ve sonraki uygun takip adımlarını izler.
9. **E-01/E-02/E-12** süreç boyunca yöntem, maliyet ve sonuç kalitesini gözetir.

## Senaryo B — Açık ilanı olmayan potansiyel işveren

1. **F-02** kullanıcıyla ilgili bir şirket keşfeder.
2. **F-04** kurumun resmî kanallarını ve bağlamını araştırır.
3. **F-03** ilgili çalışma olasılığını *ilan dışı, doğrulanmamış potansiyel fırsat* olarak işaretler.
4. **F-05/F-06** uygunluğu ve iletişim kurmanın yerindeliğini değerlendirir.
5. Uygun ve izinli bir temas kanalı mevcutsa **F-07** gerçeğe dayalı kişiselleştirilmiş tanıtım hazırlar.
6. **E-07** yetki ve iletişim politikalarını uygular; **F-08** gönderimi gerçekleştirir veya vazgeçer.
7. **F-09/F-10/F-11** yanıt, takip, ret ve iletişimden çıkma taleplerini yönetir.

## Senaryo C — Belirsiz gönderim veya başarısız otomasyon

1. **F-08** formu gönderir, fakat hedef sistemden doğrulama alamaz.
2. **E-04** durumu `unconfirmed` olarak ele alır; körlemesine aynı başvuruyu tekrarlamaz.
3. **E-06/E-08** mevcut kanıtı saklar, gerekirse kontrol adımı başlatır.
4. **F-10** fırsat durumunu *gönderildiği doğrulanmadı* olarak gösterir.
5. Alternatif işlem mümkün değilse **F-12** üzerinden kullanıcıya devredilir; **E-02** gereksiz tekrar maliyetini durdurur.

---

# 7. L0 ile izlenebilirlik

Aşağıdaki bağlantılar, mevcut L0 belgesinin bölüm ve konu başlıklarına dayalı ilk izlemedir. L2'ye geçerken her alt gereksinime benzersiz kimlik bağlanacaktır.

| L0 üst hedefi | L1 karşılığı |
|---|---|
| İnternette platform bağımsız keşif ve erişim (L0 §5, §7) | F-02, F-03, F-04, F-06, F-08, E-10 |
| Kullanıcı hedefleriyle uyumlu fırsatlar (L0 §4, §5.2) | F-01, F-05, E-06, E-12 |
| Otonom, adaptif strateji (L0 §6) | F-06, F-11, E-01, E-03 |
| Doğru başvuru ve temsil (L0 §5.4, §9) | F-07, F-08, F-12, E-06, E-07 |
| Süreklilik, hafıza ve geri bildirim (L0 §8) | F-09, F-10, F-11, E-05, E-09 |
| Kaynak verimliliği (L0 §11, §14, §15) | E-01, E-02, E-03, E-12 |
| İşlem güvenliği ve izlenebilirlik (L0 §17, §20, §21) | E-04, E-07, E-08 |
| Mühendislik kalitesi, ölçeklenebilirlik (L0 §22–§24) | E-09, E-10, E-11 |

---

# 8. Kapsam sınırları ve henüz alınmayan kararlar

## 8.1. Bu L1 tanımının **içinde** olanlar

- Fırsat keşfinden gerçek ve izinli dış başvuruya kadar tüm iş yaşam döngüsü.
- İlan dışı potansiyel işveren araştırması ve uygun/ölçülü ilk temas.
- Kullanıcı kontrolü, sonuç doğrulama, takip ve sürekli çalışma.
- Model/token maliyeti, araç seçimi, güvenlik, dayanıklılık ve ölçümün çapraz kesen tasarım yükümlülüğü olması.

## 8.2. Bu L1 tanımının **dışında** olanlar

- İş teklifi, mülakat ya da kesin istihdam garantisi.
- Kullanıcının doğrulamadığı özgeçmiş/başarı/kimlik iddiaları üretmek.
- İstenmeyen toplu mesajlar veya iletişimden çıkma taleplerini yok sayan kampanyalar.
- Yetkisiz erişim, giriş korumalarını aşma, gizli kişisel verileri toplama.
- Kullanıcı izni olmadan sözleşme imzalama, ücret/pazarlık taahhüdü verme.
- Bugünden belirli sayıdaki AI agent, model, framework veya bulut servisini zorunlu ilan etmek.

## 8.3. Daha sonraki seviyelerde karara bağlanacak konular

1. **Yetki matrisi:** Hangi gönderimler tam otomatik, hangi koşullarda onaylı, hangi eylemler yasak? (L2)
2. **Fırsat kapsamı:** Tam zamanlı, freelance, danışmanlık, staj veya diğer türlerin önceliği. (L2)
3. **Nitelikli fırsat tanımı:** Asgari doğrulama, uygunluk ve kullanıcı değer kriterleri. (L2)
4. **Gönderim politikası:** Kaynak/ülke/kanal bazında limitler, tekrar ve takip kuralları. (L2)
5. **Veri yaşam döngüsü:** Saklama, silme, gizlilik, güncellik ve veri sahipliği. (L2)
6. **Ölçülebilir kalite hedefleri:** Doğruluk, geri dönüş, maliyet, süre, güvenlik eşikleri. (L2)
7. **MVP sınırı ve geliştirme sırası:** İlk sürümde hangi F ve E alanları hangi derinlikte olmalı? (L2 planlama)
8. **Teknik seçenekler:** AI modelleri, Browser Use/Playwright veya alternatifleri, veri deposu, çalışma altyapısı, UI. (L3)

---

# 9. L1'in kabulü için kontrol listesi

L1'i tamamlanmış kabul etmeden önce aşağıdaki soruların yanıtı açık olmalıdır:

- [ ] Her L0 hedefinin en az bir L1 alanı veya açıkça gerekçelendirilmiş kapsam dışı sonucu var mı?
- [ ] Fonksiyonel yeteneklerle çapraz kesen mühendislik gereksinimleri ayrılmış mı?
- [ ] Her alanın amacı, girdisi/çıktısı, sınırı ve başarının anlamı anlaşılabiliyor mu?
- [ ] İlan dışı fırsatlar ile doğrulanmış açık ilanlar karıştırılmıyor mu?
- [ ] Dış işlem yapma ve gerçek gönderimi doğrulama kabiliyeti açıkça mevcut mu?
- [ ] Gizlilik, doğruluk, yetki, iletişim etiği ve belirsiz sonuçlar ele alınmış mı?
- [ ] Token/maliyet optimizasyonu sistem genelinde ve kalite kısıtlı olarak tanımlanmış mı?
- [ ] Her yeteneği otomatik olarak ayrı AI agent'ına dönüştürmekten kaçınılmış mı?
- [ ] Gerçek dünyada başarının nasıl ölçüleceğine ilişkin L1 ilkeleri mevcut mu?
- [ ] L2'ye aktarılacak açık kararlar listelenmiş mi?

**Belge durumu:** Bu sürüm L1 için önerilen bütünsel kapsam taslağıdır. İnceleme ve onay sonrasında kimlikler sabitlenir; L2, her L1 başlığının gereksinimlerini bağımsız olarak ayrıştırır.
