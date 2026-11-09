# NIMBUSOPS

## FINAL PRODUCT REQUIREMENTS DOCUMENT

**Unified Hybrid Cloud Infrastructure Management Platform**

Versi konsolidasi 2.0 | 9 November 2026 | Status: **FINAL DRAFT — menunggu persetujuan tim/dosen**

Proyek Cloud Computing · Sekolah Vokasi Universitas Gadjah Mada

Basis: PRD kelompok v1.0, PRD product-first v1.1, PRD review teknis v1.2, serta laporan Stage B terbaru.

## Kontrol dokumen

| Atribut | Ketentuan |
| --- | --- |
| Pemilik produk | Tim NimbusOps; PIC dan persetujuan formal ditetapkan tim |
| Repository | github.com/dapvdd/NimbusOPS |
| Baseline terintegrasi | main @ 806dbe3; Stage B branch feat/real-docker-validation @ d571d69 (belum diasumsikan merged) |
| Tujuan produk | Pengelolaan host dan workload lintas private/on-premise dan public cloud melalui satu control plane |
| Batas klaim | Status implementasi dilaporkan berdasarkan hasil agent; bukan audit independen atas kode atau bukti runtime |

## 1. Ringkasan eksekutif

NimbusOps adalah platform web vendor-agnostic untuk memonitor dan mengelola host Linux serta aplikasi Docker dari satu control plane. Platform memadukan host privat/on-premise dan VM public cloud melalui agent yang menginisiasi koneksi keluar secara aman. Operator melihat telemetry, inventaris resource, status aplikasi, riwayat operasi, dan melakukan deployment/lifecycle terbatas melalui dashboard tanpa perlu SSH pada alur normal.

Strategi pengembangan bersifat product-first: satu host dan satu Nginx yang benar-benar berjalan → dua host independen → satu private host dan satu public cloud VM nyata → perluasan multi-deployment, RBAC, audit, backup/restore. Fitur yang belum diuji tidak boleh diklaim tersedia.

## 2. Masalah, pengguna, dan proposisi nilai

- Fragmentasi SSH, Docker CLI, dan dashboard cloud menyulitkan pemantauan dan tindakan yang dapat ditelusuri.
- Operator dapat salah memilih host/container dan mengganggu workload di luar cakupan.
- Status operasi, kesehatan HTTP, dan keadaan Docker dapat berbeda; produk harus menyatakan ketidakpastian secara jujur.
- Pengelolaan hybrid lintas on-premise dan public cloud memerlukan protokol, identitas, dan pengalaman operator yang konsisten.

| Persona | Kebutuhan |
| --- | --- |
| Operator mahasiswa / infra admin | Pilih environment dan host, deploy Nginx, baca bukti, lakukan start/stop aman |
| Dosen / penguji | Demonstrasi nyata, bukti terukur, batas keamanan, replikasi uji |
| Anggota tim / viewer | Observasi host, metrik dan hasil tanpa hak mutasi (role terpisah pada tahap lanjut) |
| Pemelihara | Runbook, rollback terbatas, konfigurasi, biaya, dan pemulihan |

## 3. Visi, prinsip, dan definisi hybrid

Visi: menjadi satu konsol pengelolaan infrastruktur hybrid cloud yang ringan, dapat diperiksa, dan tidak bergantung pada satu provider. “Hybrid” hanya dinyatakan tercapai bila sekurangnya satu host privat/on-premise dan satu VM pada penyedia public cloud nyata sama-sama dikelola melalui control plane yang sama dan diuji dengan koneksi aman. Dua VM lokal hanya membuktikan multi-host, bukan hybrid public/private.

- Agent outbound-only; tidak membuka Docker TCP API atau shell arbitrer.
- Operasi dibatasi oleh template, identitas deployment, dan kepemilikan resource.
- Observasi nyata dan bukti per aksi; UNKNOWN lebih tepat daripada sukses tanpa verifikasi.
- Portabilitas, biaya terkendali, dan keamanan minimal sebelum akses lintas jaringan.
- Tidak menjanjikan provisioning VM, Kubernetes, HA, atau autoscaling pada MVP.

## 4. Ruang lingkup dan roadmap rilis

| Milestone | Ruang lingkup | Kriteria gate |
| --- | --- | --- |
| M0 — Alignment | PRD final, PIC, lingkungan uji, batas biaya, arsitektur | Disetujui tim dan dosen |
| M1 — v0.1 Single-host | Ubuntu host, agent, telemetry, Nginx deploy/start/stop, auth operator, inventory, bukti operasi | AC-01–14 dan AC-19 sesuai prioritas dan bukti nyata |
| M2 — v0.2 Multi-host | Dua host independen, stable installation identity, environment grouping, host-specific URL, isolation, recovery | AC-15 dan uji isolasi lintas host |
| M3 — v0.3 Hybrid | Private host + VM public cloud, secure tunnel/HTTPS, monitoring & deploy di keduanya | AC-16, anggaran dan teardown tercatat |
| M4 — v1.0 Advanced (opsional) | RBAC penuh, actor audit, multi-deploy parallel/sequential, Compose terbatas, backup/restore Restic S3/MinIO | AC-17/18 dan kriteria fitur tambahan terukur |

Ketergantungan provider tidak boleh menghentikan M1/M2. Jika public cloud belum tersedia, demo multi-host lokal boleh dilakukan tetapi diberi label simulasi, bukan hybrid nyata.

## 5. Arsitektur sistem

Browser React/Vite → FastAPI control plane → SQLite persisten → authenticated outbound polling/telemetry dari Python agent → Docker CLI lokal (argv tetap, shell=False) → container Nginx yang disetujui. Agent tidak menerima arbitrary command. Control plane tidak menjalankan Docker langsung pada host terkelola. Transport lintas host harus memakai HTTPS atau tunnel privat aman (misalnya Tailscale yang dikonfigurasi dengan pembatasan akses).

| Komponen | Implementasi MVP | Arah pengembangan |
| --- | --- | --- |
| Dashboard | React/Vite; overview, host, applications, operation detail | Environment selector, multi-host view, viewer role |
| Control server | FastAPI; validasi, operasi durable, agent auth | Operator auth, recovery, multi-host scheduler |
| Database | SQLite WAL dan retensi metrik | PostgreSQL hanya jika kebutuhan concurrency terukur |
| Agent | Python/psutil, heartbeat, telemetry, poll, Docker CLI | Inventory periodik, worker isolation, stable host ID |
| Workloads | Allowlisted nginx-demo, Docker lifecycle | Compose template disetujui, batch deployment |
| Backup | Tidak termasuk MVP | Restic + MinIO/S3, restore teruji |

## 6. Kebutuhan fungsional utama (FR)

| ID | Fitur | Target | Kriteria inti |
| --- | --- | --- | --- |
| FR-01 | Host connectivity | M1 | ONLINE ≤90s, STALE >90–600s, OFFLINE >600s; berdasarkan waktu server. |
| FR-02 | Telemetry | M1 | CPU %, RAM/disk byte dan % dari psutil; nilai hilang bukan nol. |
| FR-03 | Inventory | M1 | Snapshot Docker terkelola, ID, label, state, observed_at; usia snapshot terlihat. |
| FR-04 | Deploy | M1 | Pilih host+approved nginx-demo; HTTP 202 operation ID; verifikasi Docker RUNNING dan HTTP 200. |
| FR-05 | Lifecycle | M1 | START/STOP dengan identitas deployment+container tervalidasi; no-op aman. |
| FR-06 | Operation feedback | M1 | QUEUED/RUNNING/SUCCEEDED/FAILED/UNKNOWN; error, evidence, timestamp, ID. |
| FR-07 | Resource protection | M1 | Verifikasi label managed+deployment, host, container; tolak shell, privileged, prune, host-root mount. |
| FR-08 | History | M1 terbatas | Operasi/event tetap terbaca setelah restart; filter lanjutan Should. |
| FR-09 | Multi-host | M2 | Dua host, ID stabil, target eksplisit, operasi A tidak mengubah B. |
| FR-10 | Hybrid | M3 | Private host+public VM nyata, protokol agent sama, transport aman. |
| FR-11 | RBAC/audit | M4 | Operator/viewer, actor ID, audit append-only, token rotation/revocation. |
| FR-12 | Backup/restore | M4 | Snapshot Restic terenkripsi ke S3-compatible; restore terisolasi, RPO/RTO. |
| FR-13 | Agent auth | M1 | Bootstrap token, agent token unik terikat host, hash server, host isolation. |
| FR-14 | Operator auth | M1 | Login atau auth gateway; API mutation terlindungi, expiry/logout, CSRF bila cookie. |
| FR-15 | Idempotency/recovery | M1→M2 | Atomic claim, dedup concurrent, bounded RUNNING, UNKNOWN+manual verification; fencing/reconcile M2. |
| FR-16 | Freshness | M1 | recorded_at+received_at, clock skew validation, telemetry freshness terpisah dari heartbeat. |
| FR-17 | Template policy | M1 | Allowlist image/port/label; catat image digest teruji; jangan izinkan Compose bebas. |
| FR-18 | Application URL | M1→M2 | URL sesuai host/network; probe agent ≠ browser reachability. |
| FR-19 | Environment inventory | M2 | Group host berdasarkan private/public dan tampilkan metadata provider tanpa menyimpan secret di browser. |
| FR-20 | Multi-deployment | M4 | Parallel/sequential terkontrol, status per host, stop-on-failure, tidak ada rollback stateful otomatis. |

## 7. Model data dan kontrak operasi

Entitas: Host(UUID, installation identity, hostname, OS, last_seen_at); Telemetry(host_id, recorded_at, received_at, CPU, RAM, disk); DeploymentTemplate(key, image, digest, port, approved); ManagedDeployment(UUID, host_id, template_key, container ID/name); DeploymentOperation(UUID, host_id, deployment_id, action, status, timestamps, result/error); OperationEvent; AgentCredential; InventorySnapshot; OperatorSession (target M1).

| Status | Makna |
| --- | --- |
| QUEUED | Tersimpan, belum dieksekusi; HTTP 202 bukan keberhasilan workload |
| RUNNING | Diklaim agent; hasil belum terverifikasi |
| SUCCEEDED | Bukti sesuai aksi dan identitas target tervalidasi |
| FAILED | Kegagalan terobservasi dengan error code |
| UNKNOWN | Hasil tidak pasti; perlu inspeksi sebelum retry |

Jaminan tepat-sekali efek Docker tidak diasumsikan hanya dari atomic claim. Hasil terminal tidak ditimpa ulang. Backend memvalidasi bukti sesuai aksi; JSON hasil harus valid dan tidak terpotong. Operasi macet membutuhkan jalur UNKNOWN yang aman dengan verifikasi bahwa worker lama tidak lagi berjalan.

## 8. API dan kontrak integrasi

Namespace baseline /api/v1. Browser: GET /health, /hosts, /hosts/{id}, /hosts/{id}/metrics, /templates, /applications, /applications/{id}/container-state, /operations/{id}; POST /applications/deploy, /applications/{id}/start, /applications/{id}/stop. Agent: POST /agents/enroll, /agents/heartbeat, /agents/telemetry, /agents/commands/poll, /agents/commands/{id}/result. Endpoint /agents/inventory dan auth login/session/logout adalah target, belum diasumsikan tersedia.

HTTP 202 = operasi diterima; 401 = tidak sah; 403 = target dilarang; 404 = tidak ditemukan; 409 = konflik; 422 = input/bukti tidak valid; 503 = host tidak siap. Error terstruktur memakai code/message tanpa token. Perubahan kontrak wajib sinkron backend, agent, frontend, docs, dan tests.

## 9. Persyaratan keamanan dan isolasi

- Autentikasi operator sebelum API mutasi dapat diakses peserta demo atau jaringan bersama; jangan membuka endpoint unauthenticated ke LAN, Tailscale, atau internet.
- Agent token unik per host; enrollment terkendali; token plaintext tidak muncul di log/browser; file rahasia berizin terbatas.
- Verifikasi host, deployment ID, container ID, dan label nimbusops.managed serta nimbusops.deployment sebelum START/STOP.
- Allowlist image, port, parameter Docker; tidak ada privileged container, mount host-root, shell bebas, docker prune, atau Docker TCP API publik.
- TLS atau tunnel aman lintas mesin; konfigurasi firewall dan access control harus diverifikasi.
- Pengujian negatif hanya pada VM disposable atau resource demo yang disetujui; DavidLab/SPECTRA adalah protected baseline dan tidak boleh menjadi target fault injection.

## 10. Non-functional requirements (NFR)

| ID | Target usulan | Bukti |
| --- | --- | --- |
| NFR-01 | Semua mutasi terautentikasi dan terotorisasi | API direct negative tests |
| NFR-02 | Data lama/hilang/UNKNOWN tidak tampak sehat | Disconnect, clock skew, lost result |
| NFR-03 | API GET p95 ≤1s; ACK ≤2s pada profil uji | ≥100 request, ukur p50/p95/error |
| NFR-04 | Metrik muncul ≤35s sejak server terima; hasil operasi ≤5s | Timestamp end-to-end |
| NFR-05 | Heartbeat tetap berjalan saat Docker job 120s | Simulasi slow pull pada VM uji |
| NFR-06 | Data dan operasi tahan restart | Controlled restart + readback |
| NFR-07 | 100 request identik tidak gandakan efek | Parallel concurrency test |
| NFR-08 | Build dari clean checkout reproducible | Fresh clone + install + build |
| NFR-09 | UI usable pada 1366×768 dan 390px | 3 user tasks + keyboard |
| NFR-10 | Tidak membuat biaya otomatis | Budget + teardown evidence |

Seluruh angka NFR adalah target usulan, bukan pengukuran. Profil mesin, jaringan, dan toleransi disetujui pada M0.

## 11. Acceptance criteria dan strategi pengujian

| ID | Kriteria |
| --- | --- |
| AC-01 | Operator auth dan API mutation tanpa sesi ditolak |
| AC-02 | Telemetry nyata dibanding OS, formula dan window sampling selaras |
| AC-03 | Inventory dan ownership cocok Docker inspect; perubahan eksternal terdeteksi |
| AC-04 | Deploy Nginx: operation ID, RUNNING, HTTP 200 dari browser operator |
| AC-05 | Lima siklus STOP/START, state dan HTTP benar tanpa container duplikat |
| AC-06 | Agent offline→STALE→OFFLINE→online, data usang diberi label |
| AC-07 | Template tak disetujui ditolak sebelum Docker mutation |
| AC-08 | Container pembanding termasuk nama mirip tanpa label tidak berubah |
| AC-09 | Port conflict/Docker unavailable/missing evidence menghasilkan status jujur |
| AC-10 | Token salah dan cross-host result ditolak |
| AC-11 | 100 permintaan paralel hanya satu efek dan konflik jelas |
| AC-12 | Agent mati setelah claim → UNKNOWN dan recovery aman |
| AC-13 | Clock skew dan slow Docker tidak mengacaukan freshness/heartbeat |
| AC-14 | Persisted operations dan clean checkout build |
| AC-15 | Dua host independen, termasuk hostname sama; deploy A tidak mengubah B |
| AC-16 | Host privat dan public VM nyata, secure transport, deploy di keduanya |
| AC-17 | Viewer denied mutations, actor audit dan credential revocation |
| AC-18 | Backup dan restore terisolasi dengan bukti RPO/RTO |
| AC-19 | HTTP gagal/URL salah/redeploy berulang tidak tampak sehat |

M1: AC-01–14 dan AC-19 sesuai kebutuhan Must; M2: AC-15; M3: AC-16; M4: AC-17–18. Semua hasil menyertakan commit, environment, waktu UTC, langkah, expected/actual, bukti API/Docker/HTTP, dan screenshot pelengkap. Test mocked tidak menggantikan real Docker.

## 12. UX dan demonstrasi akhir

Navigasi target: Overview → Environments → Hosts → Applications → Operations. UI menampilkan host target secara persisten selama aksi, operation ID, state Docker, health HTTP, last observed, serta error actionable. Data historis diberi label; status tidak mengandalkan warna saja. Alur demo: pilih private host, lihat metrik, deploy Nginx, STOP, START, tunjukkan evidence; pilih public VM dan ulangi; matikan satu agent untuk membuktikan host lain tetap berfungsi. Tahap M3 hanya dinyatakan tercapai jika cloud VM benar-benar berasal dari public provider.

## 13. Status implementasi dan rekonsiliasi sumber (9 Nov 2026)

PRD v1.2 memotret main @ 806dbe3 dan karena itu menandai Docker nyata, START/STOP, port, dan format.ts sebagai gap. Laporan Stage B yang lebih baru menyatakan branch feat/real-docker-validation @ d571d69 sudah menguji Docker nyata: enroll, telemetry, deploy Nginx, HTTP 200 via Tailscale, STOP/START, dedup, offline queue, dan cleanup. Commit 30b3b80 memperbaiki lifecycle payload; 7a1fd95 memperbaiki port 8080→18080 dan .gitignore; d571d69 memperbaiki fallback URL. SPECTRA dilaporkan tidak berubah. Semua ini status SELF-REPORTED, belum diverifikasi independen dan belum otomatis masuk main.

| Gap / area | Keputusan konsolidasi |
| --- | --- |
| G02/G03/G10 | Reported fixed/validated Stage B; konfirmasi pada merge candidate dan clean clone |
| G05/FR-18 | Port 18080 telah dipakai dalam uji; app_url untuk browser tailnet masih perlu perbaikan |
| G01/FR-14 | Operator auth tetap release blocker sebelum akses non-loopback |
| G04/G06 | Evidence validation dan ownership check tetap perlu audit/uji negatif |
| G07/G08/G09/G11/G13 | Inventory freshness, stuck RUNNING, worker scheduling, redeploy, time skew perlu verifikasi |
| G12 | Stable installation identity ditargetkan M2 |
| Review Stage B | Fresh-context reviewer belum berhasil; PR review wajib sebelum merge |

Jangan memakai port 8080 dari PRD v1.2 sebagai default baru: baseline Stage B mengubah port demo ke 18080 untuk menghindari benturan dengan SPECTRA. Port tetap harus configurable dan diverifikasi sebelum demo.

## 14. Risiko, biaya, dan tata kelola

| Risiko | Mitigasi |
| --- | --- |
| Registrasi cloud gagal | Lanjutkan M1/M2; evaluasi provider alternatif; jangan klaim M3 |
| Biaya free tier tak terduga | Budget, alert, inventaris disk/IP/egress/snapshot, teardown owner |
| Akses API tanpa auth | Bind loopback sampai auth + secure transport tersedia |
| Agent/Docker privilege | VM disposable, allowlist, ownership, negative tests |
| Operasi hilang/macat | UNKNOWN, inspeksi aman, idempotency, recovery runbook |
| Scope creep | Freeze M1; multi-deploy dan backup sebagai tahap lanjut |
| Production interference | Audit read-only; isolasi workload; jangan fault-inject DavidLab/SPECTRA |

## 15. Pembagian peran dan keputusan yang masih harus disetujui

Peran yang diperlukan: Product/Scope Lead; Backend/Auth/Data; Agent/Docker; Frontend/UX; QA/Documentation; Infrastructure/Cloud/Cost. Nama PIC, deadline UAS, provider, dan biaya belum ditetapkan dalam sumber dan wajib diputuskan tim.

- Apakah dosen mewajibkan public cloud nyata untuk nilai akhir?
- Lingkungan disposable Ubuntu/Docker mana yang disetujui untuk fault injection?
- Model operator auth (session atau trusted gateway) dan akses demo?
- Toleransi metrik, timeout operasi, policy URL, image digest, dan port final?
- Batas anggaran cloud, PIC provisioning, dan prosedur teardown?
- Kapan branch Stage B direview dan di-merge ke main?

## 16. Riwayat sumber dan kebijakan perubahan

| Sumber | Kontribusi yang dipertahankan |
| --- | --- |
| PRD_NimbusOps.docx (v1.0) | Visi hybrid, hub-spoke, 7 modul, multi-deploy, RBAC, Restic/S3, roadmap ambisius |
| NimbusOps_PRD_v1.1_Product_First_Hybrid_Ready.docx | Tahapan product-first, single-host proof, multi-host, hybrid final, scope MVP realistis |
| PRD NimbusOPS v1.2 (9 Nov 2026) | G01–G13, FR-01–18, AC-01–19, kontrak state, keamanan, pengujian, keterlacakan |
| Stage B report (9 Nov 2026) | Real Docker evidence self-reported, commits 7a1fd95/30b3b80/522f118/d571d69 |

Kebijakan: perubahan requirement harus memiliki ID, alasan, owner, target milestone, kriteria penerimaan, dan dampak ke backend/agent/frontend/tests/docs. Dokumen ini merupakan PRD final konsolidasi untuk proses review; status FINAL APPROVED baru berlaku setelah persetujuan formal tim/dosen.

---

NIMBUSOPS · Final Consolidated PRD v2.0 · 9 Nov 2026 · Review required
