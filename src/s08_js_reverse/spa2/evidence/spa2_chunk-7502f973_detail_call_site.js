// 原件片段，逐字取自 https://spa2.scrape.center/js/chunk-7502f973.428355cb.js
// UTF-8 解码后的字符区间 [7799, 8416)，原文件共 8593 字符 / 8635 字节，SHA-256 b9e1c95a1def0f34c2c91123884d62b4453e4a8f5cd11b32afad3bff4e6bb46f
// 重新取件：
//   curl -s https://spa2.scrape.center/js/chunk-7502f973.428355cb.js | python3 -c "import sys;print(sys.stdin.read()[7799:8416])"
// 以下内容为原文，未做任何改写、格式化或换行：
n=[],s=(a("a481"),a("7d92")),i=a("3e22"),o=a("1a7b"),c={name:"Detail",data:function(){return{loading:!1,key:this.$route.params.key,movie:null}},mounted:function(){this.onFetchData()},computed:{photos:{get:function(){return this.movie.photos.map((function(t){return t.replace(/(.*[(?:jpg)|(?:png)]).*/,"$1")}))}}},methods:{transfer:i["a"],onBuy:function(){window.location="https://maoyan.com/"},onFetchData:function(){var t=this;this.loading=!0;var e=o(this.$store.state.url.detail,{key:this.key}),a=Object(s["a"])(e,0);this.$axios.get(e,{params:{token:a}}).then((function(e){var a=e.data;t.loading=!1,t.movie=a}))}}},
