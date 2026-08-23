// 原件片段，逐字取自 https://spa2.scrape.center/js/chunk-10192a00.243cb8b7.js
// UTF-8 解码后的字符区间 [2008, 2652)，原文件共 2829 字符 / 2839 字节，SHA-256 ec5d655efff88175d40769314d9280aac4d4650ea00eb3923ed9bc8097804598
// 重新取件：
//   curl -s https://spa2.scrape.center/js/chunk-10192a00.243cb8b7.js | python3 -c "import sys;print(sys.stdin.read()[2008:2652])"
// 以下内容为原文，未做任何改写、格式化或换行：
n=[],i=e("7d92"),r=e("3e22"),o={name:"Index",components:{},data:function(){return{loading:!1,total:null,page:parseInt(this.$route.params.page||1),limit:10,movies:null}},mounted:function(){this.onFetchData()},methods:{transfer:r["a"],onPageChange:function(t){this.$router.push({name:"indexPage",params:{page:t}}),this.onFetchData()},onFetchData:function(){var t=this;this.loading=!0;var a=(this.page-1)*this.limit,e=Object(i["a"])(this.$store.state.url.index,a);this.$axios.get(this.$store.state.url.index,{params:{limit:this.limit,offset:a,token:e}}).then((function(a){var e=a.data,s=e.results,n=e.count;t.loading=!1,t.movies=s,t.total=n}))}}},
