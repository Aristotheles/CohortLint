# CohortLint rule registry

This file is generated from the registered runtime rules.

| ID | Category | Default severity | English | Deutsch | Türkçe |
|---|---|---|---|---|---|
| C001 | completeness | error | Required covariate absent | Erforderliche Kovariate fehlt | Gerekli kovaryat yok |
| C002 | completeness | warning | High missingness | Hoher Anteil fehlender Werte | Yüksek eksiklik oranı |
| C003 | completeness | warning | Differential missingness | Differentielle Fehlwerte | Diferansiyel eksiklik |
| D001 | design | warning | Batch-condition association | Assoziation zwischen Batch und Bedingung | Batch-koşul ilişkisi |
| D002 | design | error | Complete or level-specific confounding | Vollständige oder stufenspezifische Konfundierung | Tam veya düzeye özgü konfunding |
| D003 | design | error | Rank-deficient design matrix | Rangdefiziente Designmatrix | Rank eksik tasarım matrisi |
| D004 | design | warning | Multicollinearity among covariates | Multikollinearität zwischen Kovariaten | Kovaryatlar arası multicollinearity |
| D005 | design | warning | Group size imbalance | Unausgewogene Gruppengrößen | Grup büyüklüğü dengesizliği |
| D006 | design | info | Integrability score | Integrationsfähigkeit | Entegre edilebilirlik skoru |
| P001 | privacy | error | Residual direct identifiers | Verbleibende direkte Identifikatoren | Kalan doğrudan tanımlayıcılar |
| P002 | privacy | warning | k-anonymity violation | Verletzung der k-Anonymität | k-anonimlik ihlali |
| P003 | privacy | warning | Excessive date precision | Übermäßige Datumsgenauigkeit | Aşırı tarih hassasiyeti |
| S001 | structural | error | Sample identifier integrity | Integrität der Stichprobenkennung | Örnek tanımlayıcı bütünlüğü |
| S002 | structural | warning | Possible observation-level mixing | Mögliche Vermischung der Beobachtungsebenen | Olası gözlem düzeyi karışması |
| S003 | structural | warning | Schema drift across cohorts | Schemaabweichung zwischen Kohorten | Kohortlar arası şema kayması |
| S004 | structural | error | Type disagreement | Abweichende Datentypen | Veri tipi uyuşmazlığı |
| U001 | units | error | Numeric unit drift | Abweichende numerische Einheiten | Sayısal birim kayması |
| U002 | units | warning | Categorical encoding drift | Abweichende kategoriale Kodierung | Kategorik kodlama kayması |
| U003 | units | error | Decimal separator artifact | Artefakt durch Dezimaltrennzeichen | Ondalık ayırıcı artefaktı |
| U004 | units | warning | Scale mismatch | Abweichende Skalierung | Ölçek uyuşmazlığı |
| U005 | units | warning | Out-of-range values | Werte außerhalb des Bereichs | Aralık dışı değerler |
| V001 | vocabulary | warning | Unmapped ontology terms | Nicht zugeordnete Ontologiebegriffe | Eşlenmemiş ontoloji terimleri |
| V002 | vocabulary | info | Low-confidence ontology mapping | Ontologiezuordnung mit geringer Konfidenz | Düşük güvenli ontoloji eşlemesi |
| V003 | vocabulary | warning | Near-duplicate ontology labels | Nahezu doppelte Ontologiebezeichnungen | Yakın yinelenen ontoloji etiketleri |
