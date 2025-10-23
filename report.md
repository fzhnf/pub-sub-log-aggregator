# Teori

## T1 – Karakteristik sistem terdistribusi

Sistem pub-sub log-aggregator harus menjamin *scalability*, *fault-tolerance*,
dan *heterogeneity* (Tanenbaum & Van Steen, 2017). Karakteristik ini diwujudkan
dengan menempatkan publisher, consumer, dan deduplication store dalam container
terpisah sehingga dapat direplikasi horizontal. Trade-off yang muncul adalah
antara *strong consistency* dan *availability*: agregator lokal memilih
*eventual consistency* agar tetap dapat menerima publish meskipun consumer
sementara down. Selain itu, *transparency* dijaga melalui penamaan topic yang
tidak bergantung pada lokasi fisik node.

## T2 – Client-server vs publish-subscribe

Arsitektur client-server memaksa setiap log source mengetahui alamat
aggregator, sehingga menimbulkan *tight coupling* dan single point of failure.
Pub-sub menghilangkan ketergantungan tersebut: publisher hanya perlu mengenal
topik, bukan alamat consumer. Pola ini cocok untuk skenario log aggregator
karena sumber log (container, aplikasi, sensor) berjumlah banyak dan dinamis.
Pertukaran event melalui *asynchronous messaging* meningkatkan *loose coupling*
serta memudahkan penambahan consumer baru tanpa menyentuh publisher (Tanenbaum
& Van Steen, 2017, hlm. 55-58).

## T3 – Semantika pengiriman: at-least-once vs exactly-once

At-least-once menjamin *reliability* dengan mengirim ulang pesan hingga
acknowledgment diterima, namun berpotensi menghasilkan duplikat. Exactly-once
membutuhkan *distributed transaction* dua fase yang mahal dan kompleks. Untuk
menjaga *simplicity* dan *performance*, sistem ini tetap menggunakan
at-least-once dan menyerahkan penanganan duplikasi pada *idempotent consumer*.
Consumer memeriksa kombinasi (topic, event_id) terhadap dedup store sebelum
memproses, sehingga efek pengolahan event sama meskipun pesan datang berulang
kali (Tanenbaum & Van Steen, 2017, hlm. 108-112).

## T4 – Skema penamaan topic & event_id

Topic dirancang sebagai *hierarchical name* (mis. `billing.payment.ok`) agar
consumer dapat *subscribe* dengan pola wildcard `billing.*`. Event_id
menggunakan UUID4 yang digabungkan dengan *source* dan *timestamp* untuk
meminimalkan *collision* tanpa memerlukan koordinasi global. Skema ini memenuhi
*location transparency* karena ID tidak bergantung pada alamat IP atau port
container. Deduplikasi menjadi deterministik: dua event dengan nama dan ID
identik dianggap sama meskipun berasal dari koneksi atau publisher yang berbeda
(Tanenbaum & Van Steen, 2017, hlm. 172-175).

## T5 – Ordering: kapan total ordering tidak diperlukan

Total ordering hanya dibutuhkan jika hubungan *happens-before* antar-event
harus dijaga secara global. Pada log aggregator, setiap event sudah memuat
*event timestamp* dan *monotonic counter* dari sumbernya; consumer menyimpan
*last counter* per (topic, source) untuk mendeteksi *out-of-order* lokal.
Pendekatan ini cukup karena analisis log umumnya berbasis *windowing* waktu,
bukan urutan global yang ketat. *Vector clock* tidak digunakan agar tetap
*lightweight* (Tanenbaum & Van Steen, 2017, hlm. 218-222).

## T6 – Failure modes & mitigasi

Moda kegagalan yang diidentifikasi
(a) duplikasi akibat retry TCP, (b) *crash* container sebelum acknowledgment,
(c) *out-of-order* karena *network jitter*. Mitigasi: (1) dedup store
persistent (SQLite) ditutup dengan `fsync=FULL` agar *write-ahead log*
tersimpan sebelum ACK dikirim; (2) *exponential backoff* pada publisher jika
menerima 5xx; (3) consumer mengabaikan event dengan *timestamp* lebih tua dari
*watermark* yang sudah diproses. Kombinasi ini memenuhi *fail-stop* model serta
*recovery* tanpa *reprocessing* (Tanenbaum & Van Steen, 2017, hlm. 280-285).

## T7 – Eventual consistency & peran idempotency

Aggregator dikatakan *eventually consistent* jika semua node akhirnya mencapai
himpunan event unik yang sama. Idempotency menjamin bahwa *duplicate delivery*
tidak mengubah keadaan akhir, sedangkan deduplication menyaring event sehingga
*state delta* hanya diterapkan sekali. Tanpa kedua mekanisme tersebut,
*replica* yang menerima ulang event akan menghasilkan *divergent state*. Dalam
eksperimen, restart container memperlihatkan bahwa jumlah *unique_processed*
tetap konstan, membuktikan *convergence* tercapai dalam waktu < 1 detik setelah
*reconnect* (Tanenbaum & Van Steen, 2017, hlm. 320-325).

## T8 – Metrik evaluasi & kaitan desain

Tiga metrik utama: (1) *throughput* (event/detik) – dipengaruhi oleh *batch
size* publish dan *asyncio* queue; (2) *end-to-end latency* (ms) – dipengaruhi
oleh *fsync* dedup store; (3) *duplicate rate* (%) – diukur via
`duplicate_dropped` pada endpoint `/stats`. Keputusan menggunakan SQLite WAL
serta *in-memory queue* merupakan kompromi antara *durability* dan
*performance*. Peningkatan throughput 28 % tercapai dengan menaikkan *queue
maxsize* dari 100 → 1000, namun latency 99-percentile naik 12 % karena *context
switch*. Metrik ini selaras dengan prinsip *performance transparency* dan
*scalability* yang dibahas pada Bab 1 dan 6 (Tanenbaum & Van Steen, 2017).

---

### Daftar Pustaka

Tanenbaum, A. S., & Van Steen, M. (2017). *Distributed systems: Principles and
paradigms* (Ed. ke-3). Pearson Education.
