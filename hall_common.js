let hallCommon = {};
hallCommon.handleBadSrc = function(dom, locale, isBig = false) {
  let src = null;
  if (locale=="en" || locale=="en-US" || locale=="EN" || locale=="en-UK") {
    src = isBig
      ? 'https://download.snec.org.cn/SNEC/article/loadingFailed-big-en-1595382602417.png'
      : 'https://download.snec.org.cn/SNEC/article/hallLogo-en-1618477267672.png';
  }
  else if(locale=="ja" || locale=="ja-JP" || locale=="japanese" || locale=="jp" ){
    src = isBig
    ? 'https://download.snec.org.cn/SNEC/article/loadingFailed-big-en-1595382602417.png'
    : 'https://download.snec.org.cn/SNEC/article/hallLogo-jp-1619334362943.png';
  }
  else
  {
    src = isBig
    ? 'https://download.snec.org.cn/SNEC/article/loadingFailed-big-cn-1595382578210.png'
    : 'https://download.snec.org.cn/SNEC/article/hallLogo-cn-1618474889206.png';
  }
  dom.src = src;
  dom.onerror = null;
};
