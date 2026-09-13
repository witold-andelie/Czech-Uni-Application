module github.com/czech-uni-apply/api

go 1.25.0

require github.com/czech-uni-apply/catalog v0.0.0

require golang.org/x/text v0.41.0 // indirect

replace github.com/czech-uni-apply/catalog => ../../services/catalog
