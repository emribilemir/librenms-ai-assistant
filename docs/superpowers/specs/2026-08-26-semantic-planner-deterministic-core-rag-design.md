# Semantic Planner, Sınırlı Deterministik Çekirdek ve RAG Tasarımı

## Amaç

LibreNMS doğal dil PoC'sinde Python'ın Türkçe intent anlamaya çalıştığı regex ve kelime listelerini kaldırmak; doğal dil yorumunu Qwen planner'a, doğrulanabilir kimlik/filtre/operasyon gerçeklerini sınırlı deterministik katmanlara vermek; katalog ve doküman bağlamını ileride RAG ile sağlayabilecek temiz bir sınır kurmak.

Bu çalışma yeni bir ürün mimarisi kurma girişimi değildir. Mevcut PoC'nin çalışan ve kanıtlanmış parçalarını koruyan küçük bir sahiplik düzeltmesidir.

## Mevcut Durum

- `librenms-hybrid-poc/planner_v2.py`, device-set sorgularını Türkçe kelime, ek ve regex kalıplarıyla tanımaya çalışıyor.
- `librenms-hybrid-poc/hybrid_poc.py`, bu deterministik dil yolunu Qwen planner'dan önce çalıştırıyor.
- `hybrid-gold-v3/resolver_candidate_v5.py`, yapılandırılmış `brand`, `family`, `port_count` ve `poe` filtrelerini katalog üzerinde uygulayabiliyor; ham Türkçe intent çözmesi gerekmiyor.
- Resolver v5; katalog ingest raporu, identity variant, UNKNOWN alanlar ve ambiguity korumasını içeriyor.
- EMR-43 coverage manifestosu `hybrid_poc.py` içinde zaten mevcut.
- EMR-43'ün v4 resolver'a eklemek istediği ham Türkçe port/marka/PoE facet parser'ı mevcut `main`e alınmamış ve bu tasarım kapsamında alınmayacak.
- Kullanıcıya ait takip edilmeyen `librenms-planner-v3-poc/` klasörü semantic-planner deneyidir; uygulama sırasında değiştirilmez veya takip altına alınmaz.

## Sahiplik Sınırı

### Qwen semantic planner

Qwen yalnızca kullanıcının doğal dilini yapılandırılmış bir plana çevirir:

```json
{
  "request_type": "atomic_fact | ports | alerts | events | device_set | investigation | historical_investigation | unsupported",
  "intent": "device_status | device_ports | device_alerts | device_events | device_set | investigation | historical_status | unsupported | unknown",
  "device_query": "ham referans veya null",
  "device_filters": {
    "brand": "string veya null",
    "family": "string veya null",
    "port_count": "pozitif integer veya null",
    "poe": "boolean veya null"
  }
}
```

Planner:

- intent ve route semantiğini anlar;
- negation dahil doğal dil filtrelerini çıkarır;
- açık hostname/SKU/model referansını değiştirmeden taşır;
- cihaz seçmez, durum iddia etmez ve backend aracı çağırmaz.

### Python plan doğrulayıcı

Python doğal dili yorumlamaz. Yalnızca:

- JSON nesnesi ve zorunlu alanları doğrular;
- enum ve alan tiplerini doğrular;
- `request_type` ile `intent` eşleşmesini doğrular;
- device-set dışındaki rotalarda ürün filtrelerinin boş olmasını zorunlu tutar;
- boş veya geçersiz planı çalıştırmak yerine güvenli `unknown` sonucuna dönüştürür.

Doğrulayıcı, geçersiz planı yeni Türkçe kelime kurallarıyla “düzeltmeye” çalışmaz.

### Resolver v5

Resolver yalnızca:

- açık hostname/SKU/model referanslarını eşleştirir;
- katalogdan üretilmiş identity variant adaylarını bulur;
- yapılandırılmış filtreleri katalog alanlarına uygular;
- tekil, belirsiz ve eşleşmeyen sonuçları ayırır;
- UNKNOWN katalog alanlarını tahmin etmez.

Fuzzy eşleştirme, serbest Türkçe cümle üzerinde değil sonlu katalog kimlikleri üzerinde çalışır. Bir SKU/model birden fazla fiziksel cihazı gösteriyorsa otomatik cihaz seçilmez.

### Backend ve cevap üretimi

Backend operasyonel gerçeğin tek sahibidir:

- `get_device`
- `get_ports`
- `get_alerts`
- `get_events`

Atomik durum cevapları backend sonucundan deterministik üretilir. Investigation rotasında araç kümesi sabit Level-1 kapsamıyla sınırlıdır; Qwen yalnızca alınmış kanıtı sentezler.

## Veri Akışı

```text
Kullanıcı sorgusu
  -> Qwen semantic planner
  -> katı plan doğrulama
  -> resolver v5
  -> unique / clarification / no_match
  -> read-only backend araçları
  -> atomik rotada deterministik cevap
     veya investigation rotasında bounded synthesis
```

Planner başarısızlığında resolver'a tüm kullanıcı cümlesi gönderilmez. Sistem `unknown`/planner failure üretir ve yanlış aracı çalıştırmaz.

## Claude İncelemesindeki Dil Dışı Bulgular

### Korunacak, zaten uygulanmış bulgular

1. Direct retrieval için `ports`, `alerts`, `events` ve geçmiş sorgular için `historical_investigation` route'ları schema içinde bulunuyor.
2. `device_query` açık referansı verbatim taşıma kuralı prompt içinde bulunuyor.
3. Geçmiş durum soruları `unsupported` yerine tarihsel investigation yoluna gidebiliyor.
4. `planner_llm_called` ve `synthesis_llm_called` ayrı kaydediliyor.
5. Resolver v5 UNKNOWN/null katalog alanlarını `unevaluated_*` alanlarında görünür tutuyor.
6. Ambiguous SKU/model veya bir modelin birden fazla fiziksel örneği tek cihaza indirgenmiyor.
7. Investigation kanıt toplaması sabit `device + ports + alerts + events` kümesinde kalıyor.
8. Sentez girdisinde `retrieved_sources` ve `not_retrieved_sources` coverage manifestosu bulunuyor.

### Bu değişiklikte düzeltilecek bulgu

`device_set` formatlayıcısı inventory içindeki fixture `status` değerini backend çağrısı olmadan kullanıcıya yazabiliyor. Operasyonel durum backend gerçeği olduğu için device-set cevabı yalnızca model ve cihaz kimliklerini listeler; `up/down` eklemez. Device-set için toplu canlı durum istenirse bu daha sonra açık bir backend capability olarak tasarlanır.

### Bu değişiklikte genişletilmeyecek bulgular

- Filtre şemasında link hızı alanı yoktur. `speed_mbps` eklemek katalog ingest, planner schema, resolver filtresi ve ürün davranışını birlikte etkiler. Mevcut kaynakta hız bilgisi her model için güvenilir ve ayrı bir alan olarak bulunmadığından bu değişiklikte tahmin edilmeyecek.
- `48G'lerin alarmlarını göster` gibi birden fazla cihazı hedefleyen kaynak sorguları v1'de otomatik fan-out yapmayacak. Resolver sonucu birden fazlaysa clarification dönecek; toplu sorgu ayrı capability kararıdır.
- Structured synthesis findings, evidence kimlikleri ve deterministik grounding validator değerli bir sonraki aşamadır; semantic planner sahiplik değişikliğine karıştırılmayacaktır.
- Küçük JSON için 54 karakter eşiğine bağlı hybrid serialization eski T46 deneyine özgüdür. Atomik cevap artık LLM sentezinden geçmediği için bu heuristik production mimarisine taşınmayacaktır.
- Serbest metin üzerinde write-action kelime post-filter'ı eklenmeyecektir. Güvenlik, read-only tool allowlist ve backend yetkilendirmesiyle sağlanır; yeni bir dil keyword katmanı kurulmaz.

## RAG Geçiş Planı

RAG, intent sınıflandırıcısı veya canlı operasyonel gerçek kaynağı değildir. Görevi Qwen'e sorguyla ilgili sınırlı bağlam sağlamaktır.

### Aşama 1: Retrieval sözleşmesi

Tek bir arayüz tanımlanır:

```python
class ContextRetriever:
    def retrieve(self, query: str, scopes: list[str], limit: int) -> list[RetrievedChunk]:
        ...
```

Her sonuç `source_id`, `scope`, `content`, `updated_at` ve `score` taşır. Planner yalnızca `catalog` ve `capabilities` scope'larını; synthesis ise `operations_docs` scope'unu kullanabilir.

### Aşama 2: Katalog bağlamı

Hostname/SKU exact lookup ve structured catalog filtering resolver'da kalır. Embedding veya hybrid retrieval yalnızca planner'a olası katalog bağlamını top-k olarak verir; retrieval skoru tek başına cihaz seçme yetkisi taşımaz.

Sekiz modellik mevcut PoC için vector database kurulmaz. Önce aynı arayüz altında in-memory retriever kullanılır. Katalog büyüdüğünde depolama implementasyonu değiştirilebilir.

### Aşama 3: Doküman bağlamı

LibreNMS capability açıklamaları, alan anlamları ve operasyon prosedürleri chunk'lanarak retrieval katmanına eklenir. Canlı `status`, port, alert ve event sonuçları RAG'e indekslenmez; her istekte backend'den alınır.

### Aşama 4: Provenance ve grounding

Synthesis çıktısı kullanılan `source_id` ve backend evidence kimliklerini yapılandırılmış biçimde döndürür. Doğrulayıcı, cevapta kullanılan kaynakların gerçekten retrieval/coverage manifestosunda bulunduğunu kontrol eder.

## Hata Davranışı

- Geçersiz planner JSON'u: araç çağrısı yok, `planner_failure=true`.
- Geçersiz tip veya route/intent çelişkisi: plan reddedilir; Python semantik onarım yapmaz.
- Ambiguous resolver sonucu: clarification, backend çağrısı yok.
- No-match: cihaz uydurulmaz.
- Eksik katalog facet'i: UNKNOWN görünür tutulur, false veya sıfır varsayılmaz.
- Backend verisi yoksa atomik gerçek uydurulmaz.
- Retrieval kullanılamıyorsa temel semantic planner çalışabilir; canlı gerçek yolu etkilenmez.

## Test ve Doğrulama Sınırı

Kullanıcının maliyet ve süre tercihi nedeniyle tam Gold/Generated/Legacy ve LLM tekrar koşuları yapılmayacaktır.

Uygulama sırasında yalnızca:

1. semantic plan doğrulayıcı için küçük offline unit testleri,
2. Python syntax/import kontrolü,
3. resolver v5'e yapılandırılmış filtre aktarımını kanıtlayan birkaç offline orchestration testi,
4. device-set cevabının backend çağrısı olmadan durum yazmadığını doğrulayan tek hedefli test

çalıştırılır.

Mevcut pahalı sonuç dosyaları yeni koşu yapılmış gibi güncellenmez.

## Kapsam Dışı

- Yeni vector database veya embedding modeli kurmak
- Mevcut Qwen modelini değiştirmek
- Prompt'u vaka listeleriyle büyütmek
- Tam regression suite çalıştırmak
- Production LibreNMS'e bağlanmak
- Takip edilmeyen planner v3 PoC dosyalarını değiştirmek
- `speed_mbps` filtresini bu değişiklikte eklemek
- Multi-device backend fan-out eklemek

## Kabul Ölçütleri

1. `hybrid_poc.py` artık doğal dil için `try_deterministic_device_set_plan()` çağırmaz.
2. `planner_v2.py` Türkçe kelime listeleri, suffix mantığı, regex facet extraction veya fuzzy brand extraction içermez.
3. Plan schema/type/route-intent doğrulaması Python'da kalır.
4. Device-set filtreleri resolver v5'e yapılandırılmış alanlar olarak iletilir.
5. Atomik gerçek, ambiguity, no-match, read-only ve fixed investigation sınırları korunur.
6. Coverage manifestosu korunur.
7. Device-set cevabı backend çağrısı olmadan `up/down/unknown` yazmaz.
8. Kullanıcıya ait takip edilmeyen dosyalara ve mevcut `.DS_Store` değişikliğine dokunulmaz.
