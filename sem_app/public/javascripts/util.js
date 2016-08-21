$(function(){
   //ページ内のaタグ群を取得。aTagsに配列として代入。
    var aTags = $('a'); 
       //全てのaタグについて処理
	aTags.each(function(){
          //aタグのhref属性からリンク先url取得
	  var url = $(this).attr('href');
　　　//念のため、href属性は削除
	  $(this).removeAttr('href');
          //クリックイベントをバインド
	  $(this).click(function(){
	    location.href = url;
	  });
    });
});
