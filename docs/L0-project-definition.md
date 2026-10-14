# Autonomous Career Opportunity Agent

## Ana Proje Tanımı ve Mühendislik İlkeleri

| Alan | Bilgi |
|---|---|
| Belge türü | Üst düzey proje tanımı ve mühendislik çerçevesi |
| Belge seviyesi | L0 (vizyon ve ilkeler) + L1 için alan sınıflandırması |
| Sürüm | 0.1 — İlk birleştirilmiş taslak |
| Durum | Onaylı L0 vizyon ve mühendislik ilkeleri; teknik mimari ayrı L3 belgesindedir |
| Çalışma adı | Autonomous Career Opportunity Agent (ACOA) |

> **Belgenin amacı:** Ne geliştirdiğimizi, neden geliştirdiğimizi, sistemin sınırlarını, beklenen davranışını ve uyacağı temel mühendislik ilkelerini ortak bir referans hâline getirmek. Bu belge, mimari veya teknoloji seçimi yapmak için değil, bunların değerlendirileceği gereksinim zeminini oluşturmak için hazırlanmıştır.

---

# BÖLÜM I — PROJE TANIMI (SEVİYE 0)

## 1. Tek cümlelik proje tanımı

**Autonomous Career Opportunity Agent**, kullanıcının profesyonel hedefleri doğrultusunda internet ve yetkilendirilmiş dijital kaynaklarda fırsat araştıran, şirketleri ve çalışma seçeneklerini değerlendiren, uygun başvuru ve iletişim stratejileri geliştiren, bunları verilen yetkiler içinde uygulayan ve sonuçları takip ederek yaklaşımını iyileştiren, hedef odaklı otonom bir yapay zekâ sistemidir.

## 2. Temel vizyon

İş arama ve profesyonel fırsat geliştirme sürecini, kullanıcının her adımını tek tek yönetmek zorunda olduğu manuel faaliyetler toplamından çıkarıp; hedefleri, tercihleri ve sınırları kullanıcı tarafından belirlenen **sürekli, uyarlanabilir, ölçülebilir ve sonuç odaklı bir dijital temsilcilik sürecine** dönüştürmek.

Sistem yalnızca iş ilanlarını görüntüleyen, bir sitede otomatik tıklayan veya hazırlanmış metinleri gönderen bir bot olmayacaktır. Açık bir hedefe ulaşmak için araştırma yapabilen, kanıt toplayabilen, alternatif yolları değerlendirebilen, uygun yöntemleri seçebilen ve dış dünyada yetkili işlemler gerçekleştirebilen bir agent yaklaşımı benimseyecektir.

**Ana ilke:** Kullanıcı hedefi ve yetki sınırlarını belirler; sistem bu sınırlar içinde hedefe ulaşmak için kullanılacak yöntemleri seçer ve yürütür.

## 3. Çözülmek istenen problem

Geleneksel iş arama sürecinde kullanıcı genellikle şunları ayrı ayrı yapmak zorundadır:

1. Dağınık internet kaynaklarında iş ve şirket araştırması yapmak.
2. Yayımlanmış ilanları ve henüz ilan edilmemiş potansiyel fırsatları ayırt etmek.
3. Şirket ve pozisyonların kendisine uygunluğunu analiz etmek.
4. İletişim ve başvuru yöntemlerini tespit etmek.
5. Özgeçmiş, ön yazı ve başvuru yanıtlarını özelleştirmek.
6. Web formları, e-posta ve diğer uygun kanallardan başvurmak.
7. Başvuruların ve yazışmaların durumunu izlemek.
8. Yanıt alamadığında takip stratejisi belirlemek.
9. Hangi yöntemlerin işe yaradığını değerlendirip yaklaşımını değiştirmek.

Bu işlemler zaman alır, farklı araçlara dağılır ve sürekli insan dikkatine ihtiyaç duyar. Pek çok otomasyon çözümü yalnızca belirli platformların bilinen form yapılarına veya sabit iş akışlarına bağlıdır.

**Çözüm hedefi**, hem bilgi kaynaklarına hem de başvuru yöntemlerine yönelik bu dar bağımlılığı azaltmak; keşiften başvuruya, iletişimden takibe kadar olan süreci mümkün olduğunca bütünleşik ve otonom hâle getirmektir.

## 4. Hedef ve sonuç anlayışı

Sistemin birincil hedefi **olabildiğince fazla ilana başvurmak değil, kullanıcının gerçek, uygun ve değerli profesyonel fırsatlara erişimini artırmaktır.**

Başvuru adedi tek başına başarı ölçüsü değildir. Uygunluk, doğru ve tamamlanmış başvuru, ilgili kişilerle kurulan nitelikli iletişim, olumlu geri dönüş, görüşme daveti ve nihai çalışma fırsatları daha anlamlı sonuç ölçütleridir.

Sistem sonucu garanti edemez. Ancak hedefe katkı sağlayan eylemlerin kalitesini, güvenilirliğini, hızını ve kaynak verimliliğini ölçmek ve iyileştirmek üzere tasarlanacaktır.

## 5. Genel kapsam

### 5.1. Fırsat keşfi

Sistem, tek bir iş ilanı sitesine bağlı olmadan farklı açık ve yetkili bilgi kaynaklarını araştırabilir:

- Arama motorları ve genel web sayfaları.
- Şirketlerin resmî web ve kariyer sayfaları.
- Kamuya açık pozisyon duyuruları ve başvuru portalları.
- Profesyonel topluluklar, proje duyuruları ve ilgili kurumsal kaynaklar.
- Doğrudan iş ilanı bulunmayan, ancak kullanıcı için makul bir profesyonel fırsat oluşturabilecek şirketler.

Kaynakların kapsamı zamanla geliştirilebilir; sistemin kimliği herhangi bir platforma bağlanmaz.

### 5.2. Kullanıcı ve fırsat değerlendirmesi

Sistem kullanıcıya ait doğrulanmış beceri, deneyim, tercih, kısıt, hedef ve özgeçmiş bilgilerini temel alır. Fırsatların uygunluğunu, olası değerini, belirsizliğini ve önceliğini değerlendirir; neden uygun veya uygunsuz olduğuna dair açıklanabilir gerekçeler oluşturur.

### 5.3. Şirket ve iletişim araştırması

Yalnızca yayımlanmış pozisyonları değil, potansiyel işverenleri ve kurumları da araştırabilir. Kurumun faaliyet alanını, ihtiyaçlarını, başvuru kanallarını ve kamuya açık kurumsal iletişim seçeneklerini değerlendirebilir.

### 5.4. Başvuru ve iletişim

Yetkileri ve ilgili kuralları elverdiği ölçüde:

- Özgeçmiş, ön yazı ve başvuru yanıtları hazırlayabilir veya uyarlayabilir.
- Web başvuru formlarını doldurabilir ve belge yükleyebilir.
- Uygun kurumsal e-posta kanallarından kişiselleştirilmiş mesaj gönderebilir.
- Bir kurumun sağladığı alternatif başvuru veya iletişim yöntemlerini değerlendirebilir.
- Gönderim gerçekleştiğinde başarıyı doğrulayabilir; sonuç belirsizse bunu kayıt altına alır.

Sistem, özgeçmişte ve iletişimlerde kullanıcı hakkında uydurma deneyim, yetkinlik veya başarı iddiası oluşturmaz.

### 5.5. Takip ve süreklilik

İşlemleri ve yanıtları ilişkilendirir; başvuru durumunu izler; gerekli takip adımlarını belirler. Önceki araştırma ve iletişimleri hatırlayarak gereksiz tekrarları önlemeye çalışır.

### 5.6. Stratejik uyarlanabilirlik

Bir yöntem işe yaramazsa, kurallar ve yetkiler içinde alternatif yöntemleri araştırabilir. Daha önce görülmemiş bir şirket veya web sayfası, otomatik olarak görevin sonu anlamına gelmez. Sistem, durumu değerlendirip uygun bir sonraki adımı seçmeye çalışır.

## 6. Otonomi yaklaşımı

Sistem, yalnızca bir komut dizisini tekrarlamak yerine şu karar döngüsünü uygulayabilmelidir:

**Hedefi yorumla → Durumu ve kanıtları değerlendir → Alternatifleri üret → Uygun yöntemi seç → Yetki kontrolü yap → Uygula → Sonucu doğrula → Durumu güncelle → Gerekirse yeniden planla.**

Otonomi seviyesi yapılandırılabilir olmalıdır. Bir işlem tamamen otomatik yürütülebilir, kullanıcı onayına bağlanabilir veya yasaklanabilir. Özellikle dış tarafa mesaj gönderme, kişisel belge paylaşma ve bağlayıcı taahhüt gerektiren durumlar ayrı kontrol edilmelidir.

**Otonomi, sınırsız yetki demek değildir.** Sistem, hem hedeflere hem de güvenlik, gizlilik ve geçerli kurallara uygun davranmalıdır.

## 7. Araç ve platform bağımsızlığı

Proje, aşağıdakilerden herhangi birine zorunlu bağımlı olarak tanımlanmaz:

- Belirli iş platformları (ör. LinkedIn).
- Belirli AI modeli veya model sağlayıcısı.
- Belirli browser agent kütüphanesi.
- Belirli e-posta sağlayıcısı.
- Tek bir web otomasyon yöntemi.
- Belirli agent sayısı veya sabit çoklu-agent düzeni.

Araçlar **amaç değil, değiştirilebilir uygulama seçenekleridir.** Bir işlem API veya doğrudan veri işleme yoluyla güvenilir biçimde çözülebiliyorsa tarayıcı agent'ı çalıştırılması gerekmez. Bir görev tek süreçle çözülüyorsa gereksiz yeni agent yaratılmaz.

## 8. Süreklilik, hafıza ve iyileştirme

Sistem; geçmiş araştırmaları, fırsat değerlendirmelerini, başvuruları, görüşmeleri, gönderimleri, başarısız denemeleri ve yanıtları uygun veri saklama politikaları içinde tutabilmelidir.

Bu veriler:

- Aynı şirkete veya pozisyona gereksiz tekrarlı başvuruyu önlemek,
- Takip zamanlamasını belirlemek,
- Yeni bulunan bilginin önceki bilgiyle tutarlılığını değerlendirmek,
- Fırsat ve yöntem kalitesini ölçmek,
- Stratejileri kanıta dayalı biçimde iyileştirmek

için kullanılabilir.

Buradaki “öğrenme”, modelin mutlaka yeniden eğitilmesi anlamına gelmez; deneyim verisi, değerlendirme sonuçları ve strateji güncellemeleriyle de gerçekleşebilir.

## 9. Kullanıcı kontrolü ve temsil sorumluluğu

Kullanıcı profesyonel profilini ve hedeflerini tanımlar; sistem kendisine verilen yetkiler doğrultusunda bu hedefler için faaliyet yürütür.

Kullanıcı şunları yönetebilmelidir:

- Hedef, tercih ve kısıtlarını değiştirme.
- Şirket, ülke, rol veya iletişim yöntemi gibi alanları hariç tutma.
- Bağımsız yapılabilecek işlemleri belirleme.
- Maliyet, işlem sıklığı ve dış iletişim sınırları koyma.
- Devam eden görevleri durdurma ve işlem geçmişini inceleme.
- Kullanıcı adına paylaşılan bilgi ve belgeleri kontrol etme.

Sistem kullanıcıyı temsil eder; yetkilendirmeleri aşamaz, doğrulanmamış bilgiyle başvuru yapamaz ve istenmeyen toplu iletişimi teşvik edecek biçimde çalışmamalıdır.

## 10. Projenin ne olmadığı

Bu proje şu dar kategorilerden herhangi biriyle eşitlenmemelidir:

- Sadece ilan toplayan bir web scraper.
- Yalnızca tek bir platformda otomatik tıklama yapan bot.
- Sadece CV veya ön yazı üreten metin aracı.
- Sadece otomatik e-posta gönderen bir toplu mesaj sistemi.
- Kullanıcı denetimi ve yetki sınırları olmadan her dijital işlemi deneyen bir sistem.

Bu yeteneklerin bazılarını içerebilir; ancak bunlar projenin bütününü tanımlamaz.

---

# BÖLÜM II — SİSTEM GENELİ MÜHENDİSLİK İLKELERİ

## 11. Ana mühendislik ilkesi

Sistem yalnızca hedefleri gerçekleştiren bir AI çözümü değil; **kaynaklarını etkin yöneten, karar kalitesini sınayan, davranışı gözlemlenebilen, hatalardan kontrollü kurtulabilen, güvenli, ölçülebilir, bakım yapılabilir ve genişletilebilir bir mühendislik sistemi** olarak tasarlanmalıdır.

Model seçimi, akıl yürütme derinliği, görev ayrıştırma düzeyi, araç seçimi ve hesaplama kaynakları; **karmaşıklık, belirsizlik, risk, beklenen kalite, gecikme ve maliyet** birlikte değerlendirilerek belirlenmelidir.

**Optimizasyonun hedefi en az token tüketimi değil, kabul edilebilir kalite ve güvenlik koşullarında hedefe en yüksek verimlilikle ulaşmaktır.**

## 12. Fonksiyonel yetenekler ile mühendislik gereksinimlerinin ayrımı

### Fonksiyonel yetenekler — Sistem ne yapar?

Fırsat keşfi, şirket araştırması, eşleştirme, CV uyarlama, başvuru gerçekleştirme, e-posta iletişimi, başvuru takibi ve sonuç değerlendirmesi.

### Sistem geneli mühendislik gereksinimleri — Sistem bunu nasıl bir kaliteyle yapar?

Kaynak verimliliği, güvenilirlik, yetki kontrolü, karar doğruluğu, izlenebilirlik, test edilebilirlik, performans, ölçeklenebilirlik, sürdürülebilirlik ve operasyonel kontrol.

**Kritik ayrım:** Token optimizasyonu tek bir agent'ın özelliği değil; sistem çapında geçerli bir gereksinimdir. Aynı şekilde güvenlik, gözlemlenebilirlik ve hata yönetimi de tüm fonksiyonel bileşenleri kapsar.

## 13. On iki temel mühendislik alanı

| No | Alan | Temel sorumluluk |
|---|---|---|
| 1 | Adaptive Intelligence | Göreve uygun model, akıl yürütme seviyesi ve yöntemin seçilmesi |
| 2 | Resource & Cost Optimization | Token, model/API, tarayıcı, CPU/GPU, bellek, zaman ve bütçe yönetimi |
| 3 | Agent & Task Orchestration | Görevlerin planlanması, bölünmesi, yürütülmesi ve koordinasyonu |
| 4 | Reliability & Fault Tolerance | Kesintiye dayanıklılık, hata sınıflandırması, tekrar deneme ve toparlanma |
| 5 | Memory & Context Engineering | Doğru bilginin saklanması, geri çağrılması ve doğru bağlama verilmesi |
| 6 | Decision & Evidence Quality | Kanıt, kaynak, belirsizlik ve karar kalitesinin yönetilmesi |
| 7 | Security & Permission Management | Kimlik, yetki, veri güvenliği ve dış etkileşim sınırları |
| 8 | Observability & Auditability | Olay, karar, işlem, maliyet ve sonuçların izlenebilir olması |
| 9 | Evaluation & Continuous Improvement | Kalite ölçümü, deneyler, regresyon testleri ve kontrollü iyileştirme |
| 10 | Modularity & Extensibility | Düşük bağımlılık, değiştirilebilir bileşenler ve açık arayüzler |
| 11 | Scalability & Performance | Artan görev hacminde verimli ve kararlı çalışma |
| 12 | Goal & Outcome Optimization | Etkinliği başvuru sayısıyla değil nitelikli sonuçlarla değerlendirme |

Bu alanlar **üst düzey sorumluluk başlıklarıdır**; henüz her biri için ayrı bir agent, servis veya mikroservis kurulması gerektiği anlamına gelmez.

## 14. Uyarlanabilir zekâ ve model yönlendirme

Sistem her görev için varsayılan olarak en güçlü veya en pahalı AI modelini kullanmamalıdır. Önce görev AI gerektiriyor mu, gerekiyorsa hangi kapasite yeterli, soruları değerlendirilmelidir.

### Önerilen mantıksal işlem seviyeleri

| Seviye | Yöntem | Örnek kullanım |
|---|---|---|
| L0 | Deterministik işlem, AI modeli yok | Veri temizleme, mükerrer kayıt, basit filtre, bilinen kuralla durum geçişi |
| L1 | Hafif model / düşük işlem maliyeti | Basit sınıflandırma, alan çıkarımı, ilk eleme |
| L2 | Orta seviye analiz | Detaylı uygunluk değerlendirmesi, CV uyarlaması, kurum araştırması |
| L3 | Yüksek akıl yürütme kapasitesi | Belirsiz fırsatlar, karmaşık kararlar, zor ve dinamik web görevleri |
| H | İnsan değerlendirmesi | Politika sınırlarını aşan, yüksek etkili veya belirsiz dış işlemler |

Bunlar **örnek soyut seviyelerdir**; gerçek modeller, servisler, eşikler ve maliyet hedefleri ileride değerlendirilecektir.

Model yönlendirmesi yalnızca agent ismine göre değil, şu etkenlere göre yapılmalıdır:

- Görev karmaşıklığı ve gereken düşünme derinliği.
- Bilgi belirsizliği ve doğrulanabilirlik.
- Hata maliyeti ve dış dünyadaki risk.
- Zaman sınırı ve istenen yanıt süresi.
- Çıktı kalitesi ve güven eşiği.
- Token/API bütçesi ve kaynak durumu.

Küçük model yeterli değilse daha güçlü yönteme **kontrollü yükseltme (escalation)** uygulanabilir. Yükseltmenin üst sınırı, durdurma ölçütü ve tekrar deneme sayısı tanımlanmalıdır.

**Agent sayısı da optimizasyon değişkenidir.** Altı sorumluluk alanı mutlaka altı LLM agent'ı demek değildir. Gereksiz agent'lar arası mesajlaşma maliyeti ve hata yüzeyi yaratır.

## 15. Kaynak, token ve maliyet yönetimi

Kaynak optimizasyonu yalnızca prompt kısaltmakla sınırlandırılamaz. Değerlendirilecek yöntemler:

1. **Deterministik öncelik:** Kural, sorgu, API ve basit kodla çözülebilecek işlem için LLM çağrısı yapmamak.
2. **Model routing:** Göreve yeterli kapasitedeki modeli seçmek.
3. **Reasoning budget:** Gereksiz uzun akıl yürütmeyi sınırlamak.
4. **Context selection:** Modelin görmesi gereken minimum yeterli bağlamı seçmek.
5. **Caching:** Güvenle yeniden kullanılabilecek çıktıları tekrar üretmemek; gerektiğinde geçerlilik süresi belirlemek.
6. **Batching:** Uygun işlemleri toplu yürütmek; kalite kaybını ölçmek.
7. **Tool selection:** Tarayıcıyı yalnızca gerçekten gerekli olduğunda kullanmak.
8. **Task budgets:** Görev, çalışma döngüsü ve kullanıcı bazında maliyet/işlem sınırları koymak.
9. **Early termination:** Hedef tamamlandığında, risk sınırı aşıldığında veya ilerleme mümkün olmadığında durmak.
10. **Benefit-aware escalation:** Ek model maliyetinin beklenen kalite ve başarı katkısını değerlendirmek.

İstenen optimizasyon yaklaşımı: **Sürecin tamamındaki maliyeti, doğruluğu, gecikmeyi ve sonuca katkıyı birlikte değerlendirmek.**

## 16. Görev planlama ve orkestrasyon

Sistem üst düzey hedefleri yönetilebilir görevlere ve gerektiğinde alt görevlere ayırabilmelidir.

- Alt görevlerin girişleri, beklenen çıktıları ve tamamlanma ölçütleri belirlenmelidir.
- Bağımlılıklar ve yürütme sırası yönetilmelidir.
- Bağımsız görevler gerekli ve güvenli olduğunda paralelleştirilebilmelidir.
- Görevler yeniden planlanabilir, iptal edilebilir veya durdurulabilir olmalıdır.
- Bir alt görevin tamamlanması, üst hedefin otomatik olarak tamamlandığı anlamına gelmemelidir.
- Koordinasyon maliyeti üretilen faydayı aştığında süreç sadeleştirilmelidir.

Mimari başlangıçta olabildiğince basit tutulmalı; gerçek gereksinimler ortaya çıktıkça çoklu-agent koordinasyonu veya daha karmaşık orkestrasyon eklenmelidir.

## 17. Hata toleransı, durum yönetimi ve işlem bütünlüğü

Dış dünyada işlem yapan bir agent için bir hatanın gerçek etkisi olabilir. Özellikle e-posta, form gönderimi ve belge paylaşımı gibi eylemler güvenilirlik gerektirir.

- Çalışma durumu gerektiğinde kalıcı tutulmalıdır (**durable execution**).
- Geçici hata, kalıcı hata, sonuç belirsizliği ve kullanıcı müdahalesi gerektiren durumlar ayrılmalıdır.
- Her adımın zaman aşımı ve tekrar deneme politikası olmalıdır.
- Dış işlemden önce mümkün olduğunda mükerrerlik kontrolü yapılmalıdır.
- **Idempotency** mümkün olan iş adımlarına uygulanmalıdır.
- Gönderim sonucu belirsizse, tekrar göndermeden önce sonuç doğrulanmaya çalışılmalıdır.
- Duraklama ve kurtarma işlemleri veri bütünlüğünü bozmamalıdır.
- Sistemin güvenle devam edemediği durumda kontrollü durdurma ve insan müdahalesi yolu bulunmalıdır.

Örnek: E-posta gönderildikten sonra API zaman aşımına uğrarsa agent aynı e-postayı körlemesine tekrar göndermemeli; gönderim durumunu doğrulamaya çalışmalıdır.

## 18. Hafıza, veri ve bağlam mühendisliği

Üç farklı bilgi katmanı kavramsal olarak ayrılmalıdır:

| Bilgi türü | Örnek | Temel ihtiyaç |
|---|---|---|
| Doğrulanmış kalıcı profil | Deneyimler, CV, beceriler, hedefler, izinler | Kaynak, geçerlilik ve sürüm takibi |
| Operasyonel durum | Şirket, fırsat, başvuru, e-posta, görev, sonuç | Tutarlılık, tekrar önleme ve izlenebilirlik |
| Geçici çalışma bağlamı | Açık sayfa içeriği, ara araştırma, geçici çıkarımlar | Gerektiğinde erişim, özetleme ve temizleme |

Başlıca ilkeler:

- Her agent tüm verileri görmemelidir; yalnızca görev için gerekli bağlam verilmelidir.
- Kullanıcının doğruladığı bilgiler ile web'den elde edilen iddialar ayrı tutulmalıdır.
- Kaynak, zaman ve güven düzeyi mümkün olduğunca korunmalıdır.
- Güncelliğini yitiren bilgi tekrar doğrulanmalı veya kullanılmamalıdır.
- Bellek yönetimi maliyet optimizasyonuna ve gizliliğe birlikte hizmet etmelidir.
- Saklama ve silme politikaları belirlenmelidir.

## 19. Karar kalitesi ve kanıta dayalı çalışma

Araştırma çıktısı ile kesin doğrulanmış bilgi birbirine karıştırılmamalıdır. Sistem:

- Kaynakların niteliğini ve güncelliğini değerlendirmeli.
- İlgili bilginin kullanıcıdan mı, resmî kaynaktan mı, üçüncü taraf web içeriğinden mi geldiğini ayırt etmeli.
- Belirsizlikleri kayıt altına almalı ve gerektiğinde yeni kanıt istemeli.
- Uygunluk kararını açıklanabilir gerekçelere dayandırmalı.
- Yanlış olumlu ve yanlış olumsuz değerlendirmeleri ayrı ayrı ölçmeli.
- Gerçekte gönderilmemiş bir başvuruyu gönderilmiş gibi raporlamamalı.

Kritik işlemlerde yalnızca modelin kendi güven beyanına dayanmak yerine haricî doğrulama ve somut işlem kanıtı aranmalıdır.

## 20. Güvenlik, izinler, gizlilik ve politika yönetimi

Sistem kullanıcı adına dış dünya ile etkileşeceği için yetki sınırları yalnızca prompt metninde değil, teknik olarak denetlenebilir kontrollerde de karşılık bulmalıdır.

- **En az yetki (least privilege):** Her araç ve alt sisteme gereken asgari erişim verilmeli.
- **Açık yetkilendirme:** Dış iletişim, başvuru gönderimi, belge yükleme ve hesap işlemleri tanımlı izinlere bağlı olmalı.
- **Güvenilmeyen web içeriği:** Web sayfasındaki metinler kullanıcı veya sistem talimatı gibi çalıştırılmamalı; prompt injection riski ele alınmalı.
- **Veri koruma:** CV, kişisel ve hesap bilgileri güvenli tutulmalı; sırlar ve kimlik bilgileri loglara yazılmamalı.
- **Doğruluk:** Kullanıcı profiline ilişkin uydurma veya yanlış beyan engellenmeli.
- **İletişim politikası:** Mükerrer gönderimler, istenmeyen toplu e-postalar ve reddedilmiş iletişim talepleri kontrol edilmeli.
- **Uyumluluk:** Uygulanabilir gizlilik mevzuatı, iletişim kuralları, hizmet koşulları ve yetkili erişim sınırları dikkate alınmalı.
- **İnsan denetimi:** Riskli veya kapsam dışı işlem için kullanıcı müdahalesi zorunlu tutulabilmeli.

Kullanıcı bütün sistemi veya belirli eylem türlerini derhâl durdurabilmelidir (*kill switch*).

## 21. Gözlemlenebilirlik, izlenebilirlik ve denetlenebilirlik

Bir agent'ın ne yaptığı kadar **neden yaptığı, hangi bilgiye dayandığı, ne kadar kaynak tükettiği ve gerçekte ne sonuç aldığı** da anlaşılabilir olmalıdır.

- Görev ve alt görevlerin yaşam döngüsü izlenebilmelidir.
- Model/araç seçimi, çağrı sayıları, token tüketimi ve maliyetler kaydedilmelidir.
- Önemli kararların gerekçesi ve kullandığı kanıtların referansı bulunmalıdır.
- Başvuru ve mesajların durum geçişleri doğrulanabilir olmalıdır.
- Hata ve yeniden deneme olayları ayırt edilebilir biçimde loglanmalıdır.
- Hassas veriler gözlemlenebilirlik altyapısına gereksiz aktarılmamalıdır.
- Kullanıcıya sunulan raporlar gerçekten gerçekleşen olaylarla tutarlı olmalıdır.

## 22. Test, değerlendirme ve sürekli iyileştirme

Agent kalitesi yalnızca kod testleriyle ölçülemez. Farklı değerlendirme katmanları gereklidir:

- Birim testleri ve bileşen sözleşme testleri.
- Araç, model sağlayıcısı ve veri entegrasyonu testleri.
- Sahte/dry-run başvuru senaryoları.
- Karmaşık veya değişken sayfa yapıları üzerinde kontrollü testler.
- Hata, kesinti, belirsiz gönderim ve yeniden başlatma senaryoları.
- Model/strateji değişikliklerinde regresyon değerlendirmeleri.
- Güvenlik ve yetki sınırı testleri.
- Gerçek sonuçlardan beslenen, kontrollü ve karşılaştırmalı kalite değerlendirmeleri.

İyileştirmeler, yalnızca toplam işlem sayısına değil; doğruluk, maliyet, güvenilirlik ve sonuç kalitesine göre değerlendirilmelidir.

## 23. Modülerlik ve yazılım tasarım prensipleri

Tüm alt sistemlerde şu mühendislik ilkeleri gözetilmelidir:

| İlke | Uygulama anlamı |
|---|---|
| Separation of Concerns | Araştırma, karar, veri, dış etkileşim ve yönetim sorumluluklarını ayırma |
| Single Responsibility | Fonksiyon/modül başına odaklı sorumluluk |
| High Cohesion / Low Coupling | İlgili işlevleri bir arada tutma, bağımlılıkları azaltma |
| SOLID | Uygun olduğunda sürdürülebilir arayüz ve bileşen tasarımı |
| DRY | Tekrarlanan mantığı ortaklaştırma |
| KISS | Gereksiz karmaşıklıktan kaçınma |
| YAGNI | Kanıtlanmamış ihtiyaçlar için erken soyutlama oluşturmama |
| Configurability | Model, araç, izin ve bütçeleri koddan bağımsız yapılandırabilme |
| Testability | Bileşenleri ayrı ve birlikte test edebilme |
| Reproducibility | Karar ve testleri sürüm ve yapılandırmayla ilişkilendirme |
| Maintainability | Kapsamı kontrollü değişiklik, okunabilir ve yönetilebilir kod |
| Portability | Sağlayıcı veya çalışma ortamı değişim maliyetini azaltma |

Her yeni soyutlama veya agent, açıklanabilir bir mühendislik faydasına sahip olmalıdır.

## 24. Ölçeklenebilirlik ve çalışma performansı

Artan şirket, fırsat ve kullanıcı sayısıyla birlikte:

- Görevlerin planlanması ve önceliklendirilmesi,
- İşlem hızının kontrolü,
- Servis ve API kota sınırlarının yönetimi,
- İş yükü artışında kaynak kullanımının izlenmesi,
- Uzun süren ve kısa görevlerin birbirini engellememesi,
- Veri erişim ve işleme maliyetlerinin ölçülmesi,
- Eşzamanlı görevlerin dış işlem tekrarına yol açmaması

sağlanmalıdır.

Ölçeklenebilirlik hedefleri belirlenecek gerçek kullanım senaryolarından türetilmelidir. İlk aşamada aşırı karmaşık bir dağıtık mimari kurmak zorunlu değildir.

## 25. Sonuç kalitesi ve sistemin optimizasyon hedefi

Örnek performans göstergeleri:

| Kategori | Örnek metrik |
|---|---|
| Fırsat kalitesi | Doğru eşleştirme, yanlış eleme, nitelikli fırsat oranı |
| Operasyonel başarı | Başarısı doğrulanmış başvuru yüzdesi |
| Dış iletişim kalitesi | Doğru hedef kişi/kanal, mükerrer iletişim oranı |
| İş sonucu | Olumlu yanıt, görüşme daveti, teklif ve fırsata dönüşme oranı |
| Kaynak verimliliği | Nitelikli başvuru veya olumlu sonuç başına toplam maliyet |
| AI kullanımı | Görev/başvuru başına token, model ve araç maliyeti |
| Otonomi | İnsan müdahalesiz güvenle tamamlanan görev oranı |
| Güvenilirlik | Hata, tekrar deneme, yarım kalma, mükerrer gönderim oranı |
| Performans | Tamamlama süresi, kuyruk bekleme, kaynak tüketimi |
| Karar kalitesi | Doğrulanmış bilgi oranı, yanlış çıkarım ve kaynak hataları |

**Örnek maliyet karşılaştırması (temsili):**

| Ölçü | Sistem A | Sistem B |
|---|---:|---:|
| Toplam maliyet | 10 USD | 6 USD |
| Nitelikli başvuru | 100 | 30 |
| Nitelikli başvuru başına maliyet | 0,10 USD | 0,20 USD |

Sistem B toplamda daha ucuz olsa bile **kaliteye göre normalize edilen maliyette daha kötü** olabilir. Ayrıca olumlu yanıt ve görüşme gibi sonuç metrikleri, başvuru sayısından daha anlamlıdır.

Bu metrikler örnek ölçüm çerçevesidir. Kesin hedef, eşik ve servis seviyesi değerleri daha alt seviyelerde tanımlanacaktır.

---

# BÖLÜM III — GEREKSİNİMLERİN KADEMELİ AYRIŞTIRILMASI

## 26. En genelden en dara ilerleme yaklaşımı

Proje tanımı aşamalar hâlinde derinleştirilecektir:

| Seviye | İçerik | Yanıtladığı soru |
|---|---|---|
| **L0 — Vizyon ve ilkeler** | Problem, amaç, sınırlar, genel davranış ve mühendislik değerleri | Neyi, neden geliştiriyoruz? |
| **L1 — Yetenek ve kalite alanları** | Fonksiyonel yetenekler ve sistem genelindeki mühendislik gereksinimleri | Sistem neleri yapmalı ve hangi özellikleri taşımalı? |
| **L2 — Alt sistem gereksinimleri** | Görevler, iş kuralları, durumlar, arayüz beklentileri, veri ihtiyaçları | Bileşenler nasıl davranmalı? |
| **L3 — Teknik mimari ve tasarım** | Algoritmalar, araç/model yönlendirme, bileşen sınırları, veri modelleri | Nasıl gerçekleştireceğiz? |
| **L4 — Uygulama, test ve kabul** | Kod, senaryolar, ölçülebilir eşikler, doğrulama ve dağıtım | Doğru çalıştığını nasıl kanıtlarız? |

Bir üst seviye gereksinim, alt seviyelerde karşılık bulmalı ve testlerle izlenebilir olmalıdır. Örneğin:

**L0:** Kaynakları etkin kullanmalı → **L1:** Uyarlanabilir model ve maliyet yönetimi → **L2:** Görev başına model seçimi ve bütçe politikası → **L3:** Yönlendirme ve izleme tasarımı → **L4:** Maliyet/kalite karşılaştırma testleri.

## 27. L1'e ayrılacak iki ana eksen

### A. Fonksiyonel yetenekler

1. Kullanıcı profili, hedefler ve tercihlerin yönetimi.
2. İnternet ve şirket keşfi.
3. İlan ve fırsat tespiti.
4. Şirket ve fırsat araştırması.
5. Uygunluk, değer ve öncelik analizi.
6. Başvuru ve iletişim stratejisi belirleme.
7. Belge, CV ve iletişim içeriği hazırlama.
8. Web, form, e-posta ve diğer izinli kanallardan işlem yapma.
9. Başvuru, yanıt ve takip yönetimi.
10. Sonuç değerlendirme ve strateji iyileştirme.

### B. Sistem genelindeki kalite ve mühendislik alanları

1. Zekâ seviyesi / model yönlendirme.
2. Token ve genel kaynak optimizasyonu.
3. Görev planlama ve orkestrasyon.
4. Durum tutarlılığı ve hata toleransı.
5. Hafıza, veri ve bağlam yönetimi.
6. Kanıt, doğrulama ve karar kalitesi.
7. Güvenlik, izin ve uyumluluk.
8. Gözlemlenebilirlik ve denetim.
9. Test, değerlendirme ve sürekli iyileştirme.
10. Modülerlik ve bakım kolaylığı.
11. Performans ve ölçeklenebilirlik.
12. Sonuç odaklı optimizasyon.

**Not:** Bu başlıklar birer mantıksal alan olarak verilmiştir; henüz agent, mikroservis, klasör veya kod modülü sayısını belirlemez.

## 28. Henüz kesinleştirilmeyecek teknik kararlar

Bu belgede aşağıdaki kararlar **bilinçli olarak açık bırakılmıştır**:

- Tek agent mı, birden fazla agent mı, hibrit iş akışı mı?
- Hangi LLM'ler ve hangi yerel veya uzaktan model sağlayıcıları?
- Hangi tarayıcı otomasyon altyapısı, gerekirse browser agent katmanı?
- Arama motoru ve web araştırma entegrasyonlarının seçimi.
- Veri deposu, görev kuyruğu, zamanlayıcı ve çalışma ortamı.
- Kullanıcı arabirimi, yönetim paneli ve bildirim yöntemleri.
- Otomatik başvuru kapsamı, yetki seviyeleri ve gönderim limitleri.
- Ölçülebilir kalite eşikleri, gecikme hedefleri ve bütçeler.
- İlk sürümün (MVP) sınırları ve yayın sıralaması.

Bu kararlar L1/L2 gereksinimleri netleştirildikten sonra seçeneklerin maliyet, risk, başarı ve bakım etkileri değerlendirilerek alınmalıdır.

## 29. Gereksinim yazım ve karar disiplini

Sonraki seviyelerde her gereksinim mümkün olduğunda şu bilgileri içermelidir:

- **Kimlik:** Benzersiz gereksinim kodu.
- **Gerekçe:** Hangi amaç veya riske karşılık geldiği.
- **Davranış:** Gözlemlenebilir biçimde sistemden ne beklendiği.
- **Öncelik:** Zorunlu, önemli veya ertelenebilir olup olmadığı.
- **Bağımlılıklar:** Diğer gereksinim ve yetkilere ilişkisi.
- **Kabul kriteri:** Karşılandığının nasıl doğrulanacağı.
- **Ölçüm:** Varsa kalite, performans veya maliyet metriği.
- **Karar durumu:** Öneri, kabul edildi, ertelendi veya reddedildi.

Mühendislik kararları alınırken alternatifler, gerekçeler ve önemli ödünleşimler (trade-off) kayıt altına alınmalıdır.

---

# BÖLÜM IV — TEMEL SINIRLAR VE YÖNLENDİRİCİ KARARLAR

## 30. Şu anda benimsenen proje ilkeleri

1. **Platform bağımsızlığı:** İş keşfi ve başvuru tek bir siteyle sınırlı değildir.
2. **Gerçek dış etkileşim:** Sistem yalnızca tavsiye vermek için değil, yetki dâhilinde eylem gerçekleştirmek için tasarlanır.
3. **Otonom ama denetlenebilir davranış:** Kullanıcının hedef ve izinleri belirleyicidir.
4. **Kanıt ve doğruluk:** Araştırma iddiaları ve tamamlanmış işlemler doğrulanabilir olmalıdır.
5. **Maliyet-fayda optimizasyonu:** Token değil, kaliteli sonuç başına toplam kaynak tüketimi optimize edilir.
6. **Uygun zekâ seviyesi:** En güçlü model varsayılan yöntem değildir.
7. **Sadelik:** Her fonksiyon için ayrı bir agent zorunlu değildir; gereksiz karmaşıklıktan kaçınılır.
8. **Dayanıklılık:** Dış işlemler, tekrar denemeler, belirsiz sonuçlar ve yeniden başlatma güvenle yönetilir.
9. **Güvenlik:** Kullanıcı verisi, yetkiler ve iletişim sınırları uygulama düzeyinde korunur.
10. **İzlenebilir iyileştirme:** Kararlar ve değişiklikler ölçümlerle gerekçelendirilir.
11. **Genişletilebilirlik:** Araç, model ve sağlayıcılar gerektiğinde değiştirilebilir.
12. **Kademeli mühendislik:** Önce tanım ve gereksinim, sonra tasarım, uygulama ve doğrulama yapılır.

## 31. Nihai üst düzey tanım

**Autonomous Career Opportunity Agent**, bir kullanıcının profesyonel hedefleri için internet ve diğer yetkilendirilmiş dijital ortamlarda araştırma yapabilen; yayımlanmış ilanlarla ilan edilmemiş potansiyel fırsatları keşfedip değerlendirebilen; şirketleri, iletişim kanallarını ve başvuru alternatiflerini araştırabilen; doğru ve kişiselleştirilmiş başvuru içerikleri hazırlayıp gerekli izinler içinde web ve iletişim işlemlerini gerçekleştirebilen; süreçleri takip eden, geçmiş sonuçlardan yararlanan ve stratejisini uyarlayan hedef odaklı bir otonom yapay zekâ sistemidir.

Sistem, bu yetenekleri **değiştirilebilir araç ve model bileşenleriyle; kalite, güvenlik, yetki, güvenilirlik, maliyet ve performans ölçütlerini birlikte gözeterek** yerine getirmeyi amaçlar. Görevlerin karmaşıklığına ve riskine göre gerekli zekâ ve işlem seviyesini seçer; mümkün olduğunda daha basit ve deterministik çözümleri kullanır; gerektiğinde daha gelişmiş yöntemlere yükselir. Her işlem doğrulanabilir, izlenebilir ve kullanıcı tarafından sınırlandırılabilir olmalıdır.

**Projenin nihai amacı**, kullanıcının manuel iş arama yükünü azaltırken **nitelikli profesyonel fırsatlar ve başarılı istihdam sonuçları elde etme olasılığını**, ölçülebilir ve sürdürülebilir bir sistem aracılığıyla artırmaktır.

---

## Ek — Belge kullanım notu

Bu dosya projenin **ana kapsam ve mühendislik referansıdır**; bir yazılım geliştirme talimatnamesi, ayrıntılı mimari tasarım veya tamamlanmış gereksinim kataloğu değildir. İzleyen çalışmalar bu belgeyi temel almalı, ancak daha alt seviyedeki kararları burada verilmiş gibi varsaymamalıdır.

**Sıradaki hedef:** L1 kapsamındaki fonksiyonel yetenekleri ve sistem geneli mühendislik alanlarını ayrı ayrı ayrıştırmak, örtüşmeleri gidermek ve ölçülebilir gereksinimlere dönüştürmek.
