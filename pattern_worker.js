importScripts('pattern_detector.js?v=1');
self.onmessage=event=>{
 try{self.postMessage({rows:self.patternDetector.scan(event.data)});}
 catch(error){self.postMessage({error:String(error.message||error)});}
};
