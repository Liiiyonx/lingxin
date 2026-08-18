createApp({
setup(){
    const isLoggedIn=ref(!!localStorage.getItem('token'));
    const loginForm=reactive({username:'',password:''});
    const loginLoading=ref(false);
    const currentUser=reactive({username:'',display_name:'',role:''});
    const tk=ref(localStorage.getItem('token')||'');
    const roleLabel=computed(()=>({super_admin:'超级管理员',student_affairs:'学工处',counselor:'辅导员'})[currentUser.role]||'');

    async function api(path,opt={}){
        const h={'Content-Type':'application/json',...opt.headers};
        if(tk.value)h['Authorization']='Bearer '+tk.value;
        const r=await fetch(API+path,{...opt,headers:h});
        if(r.status===401){handleLogout();throw new Error('unauthorized');}
        return r.json();
    }

    async function handleLogin(){
        loginLoading.value=true;
        try{
            const d=await api('/auth/login',{method:'POST',body:JSON.stringify(loginForm)});
            if(d.data&&d.data.token){tk.value=d.data.token;localStorage.setItem('token',d.data.token);Object.assign(currentUser,d.data.user||{});isLoggedIn.value=true;loadDash();}else if(d.token){tk.value=d.token;localStorage.setItem('token',d.token);Object.assign(currentUser,d.user||{});isLoggedIn.value=true;loadDash();}
            else alert(d.message||d.error||'登录失败');
        }catch(e){alert('连接失败');}
        loginLoading.value=false;
    }
    function handleLogout(){tk.value='';localStorage.removeItem('token');isLoggedIn.value=false;}

    const page=ref('dashboard');
    const dash=reactive({conversations:0,emotions:0,alerts_pending:0,knowledge_docs:0,emotion_distribution:null});
    const recentAlerts=ref([]);

    async function loadDash(){
        try{const d=await api('/system/dashboard');if(d)Object.assign(dash,d);}catch(e){}
        try{const d=await api('/alert/list?limit=5');recentAlerts.value=d.items||d.alerts||[];}catch(e){}
    }

    const chatScene=ref('谈心记录');
    const chatHistory=ref([]);
    const chatInput=ref('');
    const previewUrl=ref(null);
    const selectedFile=ref(null);
    const uploadingImage=ref(false);
    const chatInputPlaceholder=computed(()=>chatScene.value==='谈心记录'?“输入对话内容，或上传聊天截图...”:'输入内容...');
    const chatLoading=ref(false);
    const chatMsg=ref(null);

    async function sendChat(){
        if(selectedFile.value){chatHistory.value.push({role:'user',content:'[\u56fe\u7247\u622a\u56fe]'});await uploadAndRecognize();return;}
        if(!chatInput.value.trim()||chatLoading.value)return;
        const m=chatInput.value;chatHistory.value.push({role:'user',content:m});chatInput.value='';chatLoading.value=true;
        await nextTick();if(chatMsg.value)chatMsg.value.scrollTop=chatMsg.value.scrollHeight;
        try{const d=await api('/conversation/organize',{method:'POST',body:JSON.stringify({scene:chatScene.value,content:m})});chatHistory.value.push({role:'assistant',content:d.result||d.content||d.error||'无法生成'});}
        catch(e){chatHistory.value.push({role:'assistant',content:'⚠ 连接失败，请确认API密钥已配置'});}
        chatLoading.value=false;
    }

    const emoLogs=ref([]);const emoResult=ref(null);
    async function loadEmotionLogs(){try{const d=await api('/emotion/logs');emoLogs.value=d.items||d.logs||[];}catch(e){}}
    async function uploadAudio(e){
        const f=e.target.files[0];if(!f)return;
        const fd=new FormData();fd.append('audio',f);
        try{const h={};if(tk.value)h['Authorization']='Bearer '+tk.value;const r=await fetch(API+'/emotion/analyze',{method:'POST',headers:h,body:fd});emoResult.value=await r.json();loadEmotionLogs();}catch(e){alert('分析失败');}
    }

    const alerts=ref([]);
    async function loadAlerts(){try{const d=await api('/alert/list');alerts.value=d.items||d.alerts||[];}catch(e){}}
    async function ackAlert(id){await api('/alert/'+id+'/acknowledge',{method:'PUT'});loadAlerts();}

    const kbStats=ref(null);
    async function uploadDoc(e){
        const f=e.target.files[0];if(!f)return;
        const fd=new FormData();fd.append('document',f);
        try{const h={};if(tk.value)h['Authorization']='Bearer '+tk.value;const r=await fetch(API+'/knowledge/upload',{method:'POST',headers:h,body:fd});const d=await r.json();alert(d.message||'上传成功');}catch(e){alert('上传失败');}
    }

    function emoColor(e){return{正常:'#67c23a',高兴:'#409eff',低落:'#909399',焦虑:'#e6a23c',烦躁:'#f56c6c',压抑:'#9b59b6',愤怒:'#e74c3c',恐惧:'#8e44ad',惊讶:'#f39c12',厌恶:'#7f8c8d',悲伤:'#2c3e50',紧张:'#e67e22'}[e]||'#909399';}
    function riskBg(l){return{high:'#f56c6c',medium:'#e6a23c',low:'#67c23a',none:'#c0c4cc'}[l]||'#c0c4cc';}
    function riskLbl(l){return{high:'高风险',medium:'中风险',low:'低风险',none:'正常'}[l]||l;}

    onMounted(()=>{if(isLoggedIn.value)loadDash();});

    function handleImageUpload(e) {
        const f = e.target.files[0];
        if (!f) return;
        selectedFile.value = f;
        previewUrl.value = URL.createObjectURL(f);
    }
    function clearImage() {
        selectedFile.value = null;
        previewUrl.value = null;
        if ($refs.imageInput) $refs.imageInput.value = '';
    }
    async function uploadAndRecognize() {
        if (!selectedFile.value || uploadingImage.value) return;
        uploadingImage.value = true;
        const fd = new FormData();
        fd.append('image', selectedFile.value);
        try {
            const h = {};
            if (tk.value) h['Authorization'] = 'Bearer ' + tk.value;
            const r = await fetch(API + '/conversation/recognize-image', {method: 'POST', headers: h, body: fd});
            const d = await r.json();
            if (d.success) {
                chatHistory.value.push({role: 'assistant', content: d.content});
            } else {
                chatHistory.value.push({role: 'assistant', content: '⚠ ' + (d.message || '图片识别失败')});
            }
        } catch (e) {
            chatHistory.value.push({role: 'assistant', content: '⚠ 图片上传失败，请检查网络'});
        }
        uploadingImage.value = false;
        clearImage();
    }
    function renderMd(text) {
        if (!text) return '';
        if (typeof marked !== 'undefined' && marked !== null && marked.parse) {
            try { return marked.parse(text); } catch(e) {}
        }
        return text.replace(/\n/g, '<br>');
    }

    return {isLoggedIn,loginForm,loginLoading,currentUser,roleLabel,handleLogin,handleLogout,page,dash,recentAlerts,loadDash,
    chatScene,chatHistory,chatInput,chatLoading,chatMsg,sendChat,
    emoLogs,emoResult,loadEmotionLogs,uploadAudio,
    alerts,loadAlerts,ackAlert,kbStats,uploadDoc,
    emoColor,riskBg,riskLbl,renderMd,previewUrl,selectedFile,uploadingImage,chatInputPlaceholder,handleImageUpload,clearImage};
}
}).mount('#app');
</script>
