const result=JSON.parse(nativeEval("return {answer:42,label:'π🎵'};"));if(result.answer!==42||result.label!=='π🎵')throw Error('fixture');nativeFinish(0);
