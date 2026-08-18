
(function(){try{
const {createApp,ref,reactive,computed,onMounted,nextTick,watch}=Vue;
const API=location.origin+'/api';

// ===== SVG 图标库 =====
const Icons={dashboard:{vb:'0 0 24 24',p:['M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z']},chat:{vb:'0 0 24 24',p:['M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z']},emotion:{vb:'0 0 24 24',p:['M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z']},alert:{vb:'0 0 24 24',p:['M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z']},knowledge:{vb:'0 0 24 24',p:['M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H8V4h12v12z']},settings:{vb:'0 0 24 24',p:['M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.49.49 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z']},students:{vb:'0 0 24 24',p:['M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z']},chart:{vb:'0 0 24 24',p:['M9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4zm2 2H5V5h14v14zm0-16H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2z']},bell:{vb:'0 0 24 24',p:['M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z']},home:{vb:'0 0 24 24',p:['M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z']},calendar:{vb:'0 0 24 24',p:['M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zM9 14H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2z']},camera:{vb:'0 0 24 24',p:['M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z']},user:{vb:'0 0 24 24',p:['M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z']},water:{vb:'0 0 24 24',p:['M12 2c-5.33 4.55-8 8.48-8 11.8 0 4.98 3.8 8.2 8 8.2s8-3.22 8-8.2c0-3.32-2.67-7.25-8-11.8zM7.83 14c.37 0 .67.26.74.62.41 2.22 2.28 2.98 3.64 3.15.43.05.79.37.79.8 0 .46-.34.83-.8.76-1.62-.21-4.12-1.24-4.72-4.48']},lightbulb:{vb:'0 0 24 24',p:['M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z']},book:{vb:'0 0 24 24',p:['M21 5c-1.11-.35-2.33-.5-3.5-.5-1.95 0-4.05.4-5.5 1.5-1.45-1.1-3.55-1.5-5.5-1.5S2.45 4.9 1 6v14.65c0 .25.25.5.5.5.1 0 .15-.05.25-.05C3.1 20.45 5.05 20 6.5 20c1.95 0 4.05.4 5.5 1.5 1.35-.85 3.8-1.5 5.5-1.5 1.65 0 3.35.3 4.75 1.05.1.05.15.05.25.05.25 0 .5-.25.5-.5V6c-.6-.45-1.25-.75-2-1z']},mood:{vb:'0 0 24 24',p:['M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z']},check:{vb:'0 0 24 24',p:['M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z']}};
function svgIcon(name,size){
    var icon=Icons[name]||Icons.dashboard;
    var s=size||20;
    var paths=icon.p.map(function(d){return '<path d="'+d+'" fill="currentColor"/>';}).join('');
    return '<svg width="'+s+'" height="'+s+'" viewBox="'+icon.vb+'" style="display:block">'+paths+'</svg>';
}

// ===== 学生数据 =====
const QUOTES=[{text:'教育不是灌满一桶水，而是点燃一把火。',author:'叶芝'},{text:'每一个不曾起舞的日子，都是对生命的辜负。',author:'尼采'},{text:'你生而不可限量，你生而心怀梦想。',author:'米歇尔·奥巴马'},{text:'最大的荣耀不在于从不跌倒，而在于每次跌倒后都能爬起来。',author:'曼德拉'},{text:'生活不止眼前的苟且，还有诗和远方。',author:'高晓松'},{text:'知人者智，自知者明。胜人者有力，自胜者强。',author:'老子'},{text:'千里之行，始于足下。',author:'老子'},{text:'学而不思则罔，思而不学则殆。',author:'孔子'},{text:'天行健，君子以自强不息。',author:'周易'},{text:'路漫漫其修远兮，吾将上下而求索。',author:'屈原'},{text:'博观而约取，厚积而薄发。',author:'苏轼'},{text:'天生我材必有用，千金散尽还复来。',author:'李白'},{text:'世上无难事，只要肯登攀。',author:'毛泽东'},{text:'stay hungry, stay foolish.',author:'乔布斯'},{text:'The only way to do great work is to love what you do.',author:'乔布斯'}];
const WORDS=[{word:'Resilience',phonetic:'/rɪˈzɪliəns/',meaning:'n. 韧性，恢复力；适应力',sentence:'She showed great resilience in overcoming difficulties.'},{word:'Ephemeral',phonetic:'/ɪˈfemərəl/',meaning:'adj. 短暂的，转瞬即逝的',sentence:'The beauty of cherry blossoms is ephemeral yet profound.'},{word:'Serendipity',phonetic:'/ˌserənˈdɪpəti/',meaning:'n. 意外发现珍奇事物的本领',sentence:'Finding this book was pure serendipity.'},{word:'Perseverance',phonetic:'/ˌpɜːrsəˈvɪrəns/',meaning:'n. 坚持不懈，毅力',sentence:'Perseverance is the key to success.'},{word:'Empathy',phonetic:'/ˈempəθi/',meaning:'n. 同理心，共鸣',sentence:'A good counselor needs empathy and patience.'},{word:'Paradigm',phonetic:'/ˈpærədaɪm/',meaning:'n. 典范，范式',sentence:'This discovery marks a paradigm shift in science.'},{word:'Eloquent',phonetic:'/ˈeləkwənt/',meaning:'adj. 雄辩的，有口才的',sentence:'She gave an eloquent speech at the ceremony.'},{word:'Tenacious',phonetic:'/təˈneɪʃəs/',meaning:'adj. 坚韧不拔的，顽强的',sentence:'His tenacious spirit helped him overcome the odds.'}];

const MOOD_LABELS={happy:'今天心情不错！保持这份好心情 😊',calm:'内心平静，岁月安好 🌿',neutral:'平常的一天，也是珍贵的一天',down:'偶尔的低落也没关系，给自己一点温暖',anxious:'别担心，一切都会好起来的 💪'};

// ===== Vue App =====
createApp({setup(){
    // --- 认证 ---
    const isLoggedIn=ref(!!localStorage.getItem('token'));
    const loginForm=reactive({username:'',password:''});
    const loginLoading=ref(false);
    const currentUser=reactive({username:'',display_name:'',role:''});
    const tk=ref(localStorage.getItem('token')||'');
    const roleLabel=computed(()=>({super_admin:'超级管理员',student_affairs:'学工处',counselor:'老师',student:'学生'})[currentUser.role]||'');
    const loginType=ref('staff');
    const showStudentRegister=ref(false);
    const studentLoginForm=reactive({student_id:'',password:''});
    const studentRegisterForm=reactive({student_id:'',name:'',password:'',confirmPassword:''});

    // --- 主题 ---
    const isDarkMode=ref(localStorage.getItem('theme')==='dark');
    function toggleTheme(){isDarkMode.value=!isDarkMode.value;document.documentElement.setAttribute('data-theme',isDarkMode.value?'dark':'');localStorage.setItem('theme',isDarkMode.value?'dark':'light');}
    if(isDarkMode.value)document.documentElement.setAttribute('data-theme','dark');

    // --- 侧边栏 ---
    const sidebarCollapsed=ref(false);const sidebarMobileOpen=ref(false);
    function toggleSidebar(){if(window.innerWidth<=768)sidebarMobileOpen.value=!sidebarMobileOpen.value;else sidebarCollapsed.value=!sidebarCollapsed.value;}

    // --- Toast ---
    const toasts=ref([]);
    function showToast(msg,type){var t={message:msg,type:type||'success'};toasts.value.push(t);setTimeout(function(){var i=toasts.value.indexOf(t);if(i>-1)toasts.value.splice(i,1);},3000);}

    // --- 通用 ---
    const page=ref('dashboard');function emoColor(e){return{正常:'#10b981',高兴:'#3b82f6',低落:'#94a3b8',焦虑:'#f59e0b',烦躁:'#ef4444',压抑:'#8b5cf6',愤怒:'#e74c3c',恐惧:'#8e44ad',惊讶:'#f39c12',厌恶:'#7f8c8d',悲伤:'#1e293b',紧张:'#e67e22'}[e]||'#94a3b8';}
    function riskBg(l){return{high:'#ef4444',medium:'#f59e0b',low:'#10b981',none:'#94a3b8'}[l]||'#94a3b8';}
    function riskLbl(l){return{high:'高风险',medium:'中风险',low:'低风险',none:'正常'}[l]||l;}
    const pageTitle=computed(()=>{
        var m={dashboard:'今日工作台',teacherChat:'师生对话',classMeeting:'班会策划',docWriting:'公文写作',alerts:'风险预警',knowledge:'知识库',system:'系统管理',students:'学生管理',emotionBoard:'情绪看板',reminders:'提醒中心',studentHome:'我的首页',studentChat:'联系老师',studentAssessment:"心理测评",studentAppointment:"预约咨询",studentProfile:"个人中心"};
        return m[page.value]||'聆心';
    });
    const todayStr=computed(()=>{var d=new Date();return d.getFullYear()+'年'+(d.getMonth()+1)+'月'+d.getDate()+'日 星期'+['日','一','二','三','四','五','六'][d.getDay()];});
    const greetingText=computed(()=>{var h=new Date().getHours();return h<6?'夜深了，注意休息 🌙':h<9?'早上好 ☀️':h<12?'上午好 🌤️':h<14?'中午好 ☀️':h<18?'下午好 🌈':'晚上好 🌙';});

    // --- API ---
    async function api(path,opt){
        var h={'Content-Type':'application/json',...opt?opt.headers:null};
        if(tk.value)h['Authorization']='Bearer '+tk.value;
        var r=await fetch(API+path,{...opt||{},headers:h});
        if(r.status===401){handleLogout();throw new Error('unauthorized');}
        return r.json();
    }

    // --- 登录 ---
    async function handleLogin(){loginLoading.value=true;try{var d=await api('/auth/login',{method:'POST',body:JSON.stringify(loginForm)});if(d.data&&d.data.token){tk.value=d.data.token;localStorage.setItem('token',d.data.token);Object.assign(currentUser,d.data.user||{});isLoggedIn.value=true;loadDash();setRole();}else if(d.token){tk.value=d.token;localStorage.setItem('token',d.token);Object.assign(currentUser,d.user||{});isLoggedIn.value=true;loadDash();setRole();}else alert(d.message||d.error||'登录失败');}catch(e){alert('连接失败');}loginLoading.value=false;}
    function handleLogout(){tk.value='';localStorage.removeItem('token');localStorage.removeItem('user_type');isLoggedIn.value=false;loginType.value='staff';}
    function setRole(){var r=currentUser.role;document.documentElement.setAttribute('data-role',r==='student'?'student':r==='super_admin'?'super_admin':'counselor');}
    async function handleStudentLogin(){loginLoading.value=true;try{var d=await api('/student/login',{method:'POST',body:JSON.stringify(studentLoginForm)});if(d.success&&d.data&&d.data.token){tk.value=d.data.token;localStorage.setItem('token',d.data.token);localStorage.setItem('user_type','student');Object.assign(currentUser,d.data.user||{});currentUser.role='student';isLoggedIn.value=true;page.value='studentHome';setRole();}else alert(d.message||'登录失败');}catch(e){alert('连接失败');}loginLoading.value=false;}
    async function handleStudentRegister(){if(studentRegisterForm.password!==studentRegisterForm.confirmPassword){alert('两次密码输入不一致');return;}if(studentRegisterForm.password.length<6){alert('密码长度至少6位');return;}loginLoading.value=true;try{var d=await api('/student/register',{method:'POST',body:JSON.stringify({student_id:studentRegisterForm.student_id,name:studentRegisterForm.name,password:studentRegisterForm.password})});if(d.success&&d.data&&d.data.token){tk.value=d.data.token;localStorage.setItem('token',d.data.token);localStorage.setItem('user_type','student');Object.assign(currentUser,d.data.user||{});currentUser.role='student';isLoggedIn.value=true;page.value='studentHome';setRole();}else alert(d.message||'注册失败');}catch(e){alert('连接失败');}loginLoading.value=false;}

    // --- 仪表盘 ---
    const dash=reactive({conversations:0,emotions:0,alerts_pending:0,knowledge_docs:0});
    const recentAlerts=ref([]);
    async function loadDash(){try{var d=await api('/system/dashboard');if(d){Object.assign(dash,d);setTimeout(renderCharts,300);}}catch(e){}try{var a=await api('/alert/list?limit=5');recentAlerts.value=a.data||a.items||a.alerts||[];}catch(e){}}

    // --- 谈心助手 ---
    const chatScene=ref('谈心记录');const chatHistory=ref([]);const chatInput=ref('');const chatInputPlaceholder=computed(()=>chatScene.value==='谈心记录'?'输入对话内容...':'输入内容...');const chatLoading=ref(false);const chatMsg=ref(null);
    async function sendChat(){if(!chatInput.value.trim()&&!selectedFile.value)return;if(selectedFile.value&&!chatInput.value.trim()){await uploadAndRecognize();return;}if(!chatInput.value.trim()||chatLoading.value)return;var m=chatInput.value;chatHistory.value.push({role:'user',content:m});chatInput.value='';chatLoading.value=true;await nextTick();if(chatMsg.value)chatMsg.value.scrollTop=chatMsg.value.scrollHeight;try{var d=await api('/conversation/organize',{method:'POST',body:JSON.stringify({scene:chatScene.value,content:m})});chatHistory.value.push({role:'assistant',content:d.result||d.content||d.error||'无法生成'});}catch(e){chatHistory.value.push({role:'assistant',content:'⚠ 连接失败，请确认API密钥已配置'});}chatLoading.value=false;}
    const previewUrl=ref('');const selectedFile=ref(null);
    function handlePaste(e){var items=(e.clipboardData||window.clipboardData).items;if(!items)return;for(var i=0;i<items.length;i++){if(items[i].type.indexOf('image')!==-1){e.preventDefault();var blob=items[i].getAsFile();selectedFile.value=blob;previewUrl.value=URL.createObjectURL(blob);return;}if(items[i].kind==='file'){e.preventDefault();var b=items[i].getAsFile();selectedFile.value=b;previewUrl.value=b.type.startsWith('image/')?URL.createObjectURL(b):'';return;}}}
    function handleFileUpload(e){var f=e.target.files[0];if(!f)return;selectedFile.value=f;if(f.type.startsWith('image/'))previewUrl.value=URL.createObjectURL(f);else previewUrl.value='';}
    function clearImage(){selectedFile.value=null;previewUrl.value='';}
    async function uploadAndRecognize(){if(!selectedFile.value)return;chatLoading.value=true;var f=selectedFile.value;var fd=new FormData();var isImage=f.type.startsWith('image/');fd.append(isImage?'image':'file',f);var displayName=f.name||(isImage?'聊天截图':'上传文件');chatHistory.value.push({role:'user',content:'[上传了 '+displayName+']'});clearImage();await nextTick();if(chatMsg.value)chatMsg.value.scrollTop=chatMsg.value.scrollHeight;try{var h={};if(tk.value)h['Authorization']='Bearer '+tk.value;var url=isImage?'/conversation/recognize-image':'/conversation/upload-document';var r=await fetch(API+url,{method:'POST',headers:h,body:fd});var d=await r.json();chatHistory.value.push({role:'assistant',content:d.content||d.message||d.error||'识别失败'});}catch(e){chatHistory.value.push({role:'assistant',content:'文件上传失败，请检查网络连接'});}chatLoading.value=false;await nextTick();if(chatMsg.value)chatMsg.value.scrollTop=chatMsg.value.scrollHeight;}

    // --- 情绪识别 ---
    const emoLogs=ref([]);const emoResult=ref(null);
    async function loadEmotionLogs(){try{var d=await api('/emotion/logs');emoLogs.value=d.data||d.items||d.logs||[];}catch(e){}}
    async function uploadAudio(e){var f=e.target.files[0];if(!f)return;var fd=new FormData();fd.append('audio_file',f);try{var h={};if(tk.value)h['Authorization']='Bearer '+tk.value;var r=await fetch(API+'/emotion/analyze',{method:'POST',headers:h,body:fd});emoResult.value=await r.json();loadEmotionLogs();}catch(e){alert('分析失败');}}

    // --- 预警 ---
    const alerts=ref([]);async function loadAlerts(){try{var d=await api('/alert/list');alerts.value=d.data||d.items||d.alerts||[];}catch(e){}}async function ackAlert(id){await api('/alert/'+id+'/acknowledge',{method:'PUT'});loadAlerts();}

    // --- 知识库 ---
    const kbStats=ref(null);async function loadKbStats(){try{var d=await api('/knowledge/stats');if(d&&d.data)kbStats.value=d.data;}catch(e){}}async function uploadDoc(e){var f=e.target.files[0];if(!f)return;var fd=new FormData();fd.append('file',f);try{var h={};if(tk.value)h['Authorization']='Bearer '+tk.value;var r=await fetch(API+'/knowledge/upload',{method:'POST',headers:h,body:fd});var d=await r.json();showToast(d.message||'上传成功','success');loadKbStats();}catch(e){showToast('上传失败','error');}}

    // --- 学生管理 ---
    const students=ref([]);const studentSearch=ref('');const showAddStudent=ref(false);const newStudent=reactive({student_id:'',name:'',gender:'',college:'',class_name:'',phone:'',notes:''});const selectedStudent=ref(null);const studentProfiles=ref([]);
    async function loadStudents(){try{var d=await api('/student/list?search='+studentSearch.value+'&per_page=100');students.value=d.data||[];}catch(e){}}async function addStudent(){try{await api('/student/add',{method:'POST',body:JSON.stringify(newStudent)});showToast('学生添加成功','success');showAddStudent.value=false;Object.assign(newStudent,{student_id:'',name:'',gender:'',college:'',class_name:'',phone:'',notes:''});loadStudents();}catch(e){showToast('添加失败','error');}}async function viewStudent(sid){try{var d=await api('/student/'+sid);selectedStudent.value=d.data;var p=await api('/student/'+sid+'/profiles');studentProfiles.value=p.data||[];}catch(e){}}async function updateStudentNotes(sid,notes){try{await api('/student/'+sid,{method:'PUT',body:JSON.stringify({notes:notes})});showToast('备注已更新','success');}catch(e){}}

    // --- 日历 ---
    const calYear=ref(new Date().getFullYear());const calMonth=ref(new Date().getMonth()+1);const calEvents=ref([]);const weekdays=['日','一','二','三','四','五','六'];
    async function loadCalendar(){try{var d=await api('/student/calendar?year='+calYear.value+'&month='+calMonth.value);calEvents.value=d.data||[];}catch(e){}}function prevMonth(){if(calMonth.value===1){calMonth.value=12;calYear.value--}else calMonth.value--;loadCalendar()}function nextMonth(){if(calMonth.value===12){calMonth.value=1;calYear.value++}else calMonth.value++;loadCalendar()}function getCalDays(){var first=new Date(calYear.value,calMonth.value-1,1);var last=new Date(calYear.value,calMonth.value,0);var days=[];for(var i=0;i<first.getDay();i++)days.push(null);for(var d=1;d<=last.getDate();d++)days.push(d);return days}function getEventsForDay(day){if(!day)return[];var ds=calYear.value+'-'+String(calMonth.value).padStart(2,'0')+'-'+String(day).padStart(2,'0');return calEvents.value.filter(function(e){return e.date===ds})}function isToday(d){var t=new Date();return calYear.value===t.getFullYear()&&calMonth.value===t.getMonth()+1&&d===t.getDate()}

    // --- 提醒 ---
    const reminders=ref([]);const showCompleted=ref(false);async function loadReminders(){try{var d=await api('/student/reminder/list');reminders.value=d.data||[];}catch(e){}}async function completeReminder(rid){try{await api('/student/reminder/'+rid+'/complete',{method:'PUT'});showToast('提醒已完成','success');loadReminders();}catch(e){}}

    // --- 情绪看板数据 ---
    const emoDashStats=reactive({total:0,highRisk:0,mediumRisk:0,avgIntensity:0});const emoDashAlerts=ref([]);
    const emoPieChart=ref(null);const emoRiskChart=ref(null);const emoTrendChart=ref(null);const emoHeatmapChart=ref(null);
    let emoPieInst=null;let emoRiskInst=null;let emoTrendInst=null;let emoHeatInst=null;
    async function loadEmotionDashboard(){
        try{var s=await api('/emotion/statistics');if(s&&s.data){emoDashStats.total=s.data.total||0;emoDashStats.highRisk=s.data.high_risk_count||0;emoDashStats.mediumRisk=s.data.medium_risk_count||0;emoDashStats.avgIntensity=s.data.avg_intensity||0}}
        catch(e){}
        try{var a=await api('/alert/list?per_page=10');emoDashAlerts.value=a.data||a.items||[]}catch(e){}
        await nextTick();renderEmoCharts();
    }
    function renderEmoCharts(){
        if(typeof echarts==='undefined')return;
        var EMO_COLORS={焦虑:'#f59e0b',压抑:'#8b5cf6',恐惧:'#ef4444',愤怒:'#e74c3c',悲伤:'#6366f1',低落:'#94a3b8',紧张:'#e67e22',正常:'#10b981',高兴:'#3b82f6',烦躁:'#f97316',惊讶:'#f39c12'};
        // 情绪分布饼图
        if(emoPieChart.value){if(emoPieInst)emoPieInst.dispose();emoPieInst=echarts.init(emoPieChart.value);
            api('/emotion/statistics').then(function(d){var dist=d&&d.data?d.data.emotion_distribution:{};var data=Object.entries(dist||{}).map(function(e){return{name:e[0],value:e[1].count||e[1]}});
            emoPieInst.setOption({tooltip:{trigger:'item',formatter:'{b}: {c} ({d}%)'},series:[{type:'pie',radius:['45%','75%'],roseType:'area',itemStyle:{borderRadius:6,borderColor:'var(--bg-secondary)',borderWidth:3},label:{fontSize:11},data:data.length?data:[{name:'暂无',value:1}],color:['#6366f1','#8b5cf6','#f59e0b','#ef4444','#10b981','#3b82f6','#e67e22','#f97316','#94a3b8','#f39c12']}]});}).catch(function(){});
        }
        // 风险等级环形图
        if(emoRiskChart.value){if(emoRiskInst)emoRiskInst.dispose();emoRiskInst=echarts.init(emoRiskChart.value);
            emoRiskInst.setOption({tooltip:{trigger:'item'},series:[{type:'pie',radius:['55%','80%'],itemStyle:{borderRadius:6},label:{formatter:'{b}\n{c}人',fontSize:12},data:[{name:'高风险',value:emoDashStats.highRisk,itemStyle:{color:'#ef4444'}},{name:'中风险',value:emoDashStats.mediumRisk,itemStyle:{color:'#f59e0b'}},{name:'低风险',value:(emoDashStats.total||0)-emoDashStats.highRisk-emoDashStats.mediumRisk,itemStyle:{color:'#10b981'}}]}]});
        }
        // 近7天趋势
        if(emoTrendChart.value){if(emoTrendInst)emoTrendInst.dispose();emoTrendInst=echarts.init(emoTrendChart.value);
            api('/emotion/trends?days=7').then(function(d){var data=d&&d.data?d.data:[];var labels=[];var vals=[];
            if(Array.isArray(data)){data.forEach(function(item){labels.push(item.date||item.day||'');vals.push(item.count||item.avg_intensity||0)})}
            emoTrendInst.setOption({tooltip:{trigger:'axis'},grid:{top:10,right:10,bottom:20,left:35},xAxis:{type:'category',data:labels.length?labels:['暂无数据'],axisLabel:{fontSize:10}},yAxis:{type:'value',axisLabel:{fontSize:10}},series:[{type:'line',data:vals.length?vals:[0],smooth:true,areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(99,102,241,0.35)'},{offset:1,color:'rgba(99,102,241,0.02)'}]}},lineStyle:{color:'#6366f1',width:2},itemStyle:{color:'#6366f1'},symbol:'circle',symbolSize:6}]});}).catch(function(){});
        }
        // 热力图日历
        if(emoHeatmapChart.value){if(emoHeatInst)emoHeatInst.dispose();emoHeatInst=echarts.init(emoHeatmapChart.value);
            api('/emotion/heatmap').then(function(d){var data=d&&d.data?d.data:[];var hData=[];
            if(data.matrix&&data.emotion_labels&&data.intensity_labels){for(var i=0;i<data.matrix.length;i++){for(var j=0;j<data.matrix[i].length;j++){hData.push([j,i,data.matrix[i][j]||0])}}
            emoHeatInst.setOption({tooltip:{formatter:function(p){return data.emotion_labels[p.value[1]]+' '+data.intensity_labels[p.value[0]]+': '+p.value[2]+'次'}},grid:{top:5,right:10,bottom:15,left:70},xAxis:{type:'category',data:data.intensity_labels||[],axisLabel:{fontSize:9},position:'top'},yAxis:{type:'category',data:data.emotion_labels||[],axisLabel:{fontSize:10}},visualMap:{min:0,max:Math.max.apply(null,hData.map(function(h){return h[2]}))||10,calculable:true,orient:'vertical',right:0,bottom:'15%',inRange:{color:['#eef2ff','#c7d2fe','#818cf8','#6366f1','#4338ca']},textStyle:{fontSize:9}},series:[{type:'heatmap',data:hData,label:{show:true,fontSize:9},emphasis:{itemStyle:{shadowBlur:10,shadowColor:'rgba(0,0,0,0.25)'}}}]})}}).catch(function(){});
        }
    }
    // --- 自定义待办 ---
    const showAddTodo=ref(false);const newTodo=reactive({title:'',category:'work_task',priority:'medium',due_date:'',description:''});
    const wpTodoStudent=computed(function(){return wp.todo_list.filter(function(t){return t.category==='student_care'})});
    const wpTodoWork=computed(function(){return wp.todo_list.filter(function(t){return t.category==='work_task'||t.category==='other'})});
    async function addCustomTodo(){
        if(!newTodo.title.trim()){showToast('请输入待办标题','error');return}
        try{await api('/workplan/todo/add',{method:'POST',body:JSON.stringify({title:newTodo.title,category:newTodo.category,priority:newTodo.priority,due_date:newTodo.due_date||null,description:newTodo.description})});showToast('待办已添加','success');newTodo.title='';newTodo.description='';loadWorkplan()}catch(e){showToast('添加失败','error')}
    }
    async function completeCustomTodo(tid){
        var id=String(tid).replace('todo_','');
        try{await api('/workplan/todo/'+id+'/complete',{method:'PUT'});showToast('已完成','success');loadWorkplan()}catch(e){showToast('操作失败','error')}
    }

    // --- ECharts ---
    const cPie=ref(null);const cTrend=ref(null);const cRisk=ref(null);let pieChart=null;let trendChart=null;let riskChart=null;
    function renderCharts(){try{if(typeof echarts==='undefined')return;if(cPie.value){if(pieChart)pieChart.dispose();pieChart=echarts.init(cPie.value);var dist=dash.emotion_distribution||{};var data=Object.entries(dist).map(function(e){return{name:e[0],value:e[1]}});pieChart.setOption({tooltip:{trigger:'item'},series:[{type:'pie',radius:['40%','70%'],label:{show:true},data:data.length?data:[{name:'暂无数据',value:1}],color:['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#3b82f6']}]});}}catch(e){}}

    function renderMd(text){if(!text)return'';if(typeof marked!=='undefined'&&marked&&marked.parse){try{return marked.parse(text)}catch(e){}}return text.replace(/\n/g,'<br>')}

    // --- 今日工作台 ---
    const wp=reactive({date:'',weekday:'',todo_list:[],todo_count:0,calendar_events:[],student_summary:{total:0,high_risk:0,medium_risk:0,low_risk:0},pending_reminders:0});const wpRiskStudents=ref([]);const wpCalYear=ref(new Date().getFullYear());const wpCalMonth=ref(new Date().getMonth()+1);
    async function loadWorkplan(){try{var d=await api('/workplan/today');if(d&&d.data){Object.assign(wp,d.data)}}catch(e){}try{var a=await api('/student/list?per_page=100');var all=a.data||[];wpRiskStudents.value=all.filter(function(s){return s.risk_level==='high'||s.risk_level==='medium'})}catch(e){}}
    async function wpCompleteTodo(rid){try{await api('/workplan/complete/'+rid,{method:'PUT'});showToast('已完成','success');loadWorkplan()}catch(e){showToast('操作失败','error')}}
    const wpCalRows=computed(()=>{var year=wpCalYear.value,month=wpCalMonth.value;var first=new Date(year,month-1,1);var last=new Date(year,month,0);var days=[];for(var i=0;i<first.getDay();i++)days.push(null);for(var d=1;d<=last.getDate();d++)days.push(d);var today=new Date();var todayStr=today.getFullYear()+'-'+String(today.getMonth()+1).padStart(2,'0')+'-'+String(today.getDate()).padStart(2,'0');var rows=[];for(var i=0;i<days.length;i+=7){var row=[];for(var j=0;j<7;j++){var day=days[i+j];if(!day){row.push(null);continue}var ds=year+'-'+String(month).padStart(2,'0')+'-'+String(day).padStart(2,'0');var events=wp.calendar_events.filter(function(e){return e.date===ds});row.push({day:day,isToday:ds===todayStr,events:events})}rows.push(row)}return rows});
    function wpCalPrev(){if(wpCalMonth.value===1){wpCalMonth.value=12;wpCalYear.value--}else wpCalMonth.value--;loadWorkplan()}function wpCalNext(){if(wpCalMonth.value===12){wpCalMonth.value=1;wpCalYear.value++}else wpCalMonth.value++;loadWorkplan()}
    function wpSelectDay(day){var ds=wpCalYear.value+'-'+String(wpCalMonth.value).padStart(2,'0')+'-'+String(day).padStart(2,'0');calDayDetail.date=ds;calDayDetail.show=true;(async function(){try{var d=await api('/workplan/day/'+ds);calDayDetail.items=d.data||[]}catch(e){calDayDetail.items=[]}})()}
    const calDayDetail=reactive({show:false,date:'',items:[]});
    async function clickCalDay(day){var ds=calYear.value+'-'+String(calMonth.value).padStart(2,'0')+'-'+String(day).padStart(2,'0');calDayDetail.date=ds;calDayDetail.show=true;try{var d=await api('/workplan/day/'+ds);calDayDetail.items=d.data||[]}catch(e){calDayDetail.items=[]}}

    // --- 表情 ---
    const emojiList=['😀','😂','🤣','😊','😍','🥰','😘','😜','🤔','😐','😢','😭','😡','😱','👍','👎','👏','💪','🙏','❤️','💔','🔥','⭐','🎉','🎊','🌸','🌺','☀️','🌈','💧','🍀','🐵','🐶','🐱','🦊','🐼','🐨','🐧','💻','📱','📚','✏️','💡','🏠','🎓','🏆','⚽','🍕','🍦','☕','🚀','✨','💯','✅','❌','❓','💤','👋','🤝'];
    const showEmoji=ref(false);
    function insertEmoji(e){newMessage.value+=e;showEmoji.value=false}
    const teacherShowEmoji=ref(false);
    function insertTeacherEmoji(e){teacherNewMsg.value+=e;teacherShowEmoji.value=false}

    // --- 学生端聊天 ---
    const messageContacts=ref([]);const selectedContact=ref(null);const chatMessages=ref([]);const newMessage=ref('');const studentUnreadCount=ref(0);const appointments=ref([]);const counselors=ref([]);const newAppointment=reactive({counselor_id:'',appointment_time:'',reason:''});

    // --- 教师端聊天 ---
    const teacherSelected=ref(null);const teacherChatMsgs=ref([]);const teacherNewMsg=ref('');const teacherUnreadCount=ref(0);const teacherMsgRef=ref(null);
    const studentSearchQuery=ref('');const studentSearchResults=ref([]);
    async function searchStudents(){
        if(!studentSearchQuery.value.trim()){studentSearchResults.value=[];return}
        try{var d=await api('/student/list?search='+encodeURIComponent(studentSearchQuery.value)+'&per_page=10');studentSearchResults.value=d.data||[]}catch(e){}
    }
    async function inviteStudent(s){
        studentSearchQuery.value='';studentSearchResults.value=[];
        try{await api('/messages/send',{method:'POST',body:JSON.stringify({contact_id:s.id,content:'老师向您发起了对话'})})}catch(e){}
        teacherSelected.value={id:s.id,name:s.name,student_id:s.student_id};
        teacherChatMsgs.value=[{id:Date.now(),content:'老师向您发起了对话',sender_type:'counselor',created_at:new Date().toISOString()}];
        loadMessageContacts();showToast('已发起对话，开始聊天吧','success')
    }
    async function selectTeacherContact(contact){teacherSelected.value=contact;guidanceResult.value=null;teacherEmotionResult.emotion='';try{var d=await api('/messages/'+contact.id);teacherChatMsgs.value=(d.data||[]).reverse();await nextTick();if(teacherMsgRef.value)teacherMsgRef.value.scrollTop=teacherMsgRef.value.scrollHeight;loadMessageContacts()}catch(e){}}
    const teacherEmotionResult=reactive({emotion:'',risk:'low',intensity:0});
    const guidanceResult=ref(null);const guidanceLoading=ref(false);
    async function analyzeCounselorGuidance(){
        if(!teacherSelected.value||!teacherChatMsgs.value.length)return;
        guidanceLoading.value=true;
        try{
            var d=await api('/messages/counselor-guidance',{method:'POST',body:JSON.stringify({
                messages:teacherChatMsgs.value.slice(-10),
                student_name:teacherSelected.value.name
            })});
            if(d.success&&d.data){guidanceResult.value=d.data;showToast('AI分析完成','success')}
        }catch(e){showToast('分析失败','error')}
        guidanceLoading.value=false
    }
    async function analyzeLastMessage(text){
        try{var d=await api('/messages/analyze-emotion',{method:'POST',body:JSON.stringify({text:text})});if(d.success&&d.data){Object.assign(teacherEmotionResult,d.data)}}catch(e){}
    }
    async function sendTeacherMsg(){
        if(!teacherNewMsg.value.trim()||!teacherSelected.value)return;
        try{await api('/messages/send',{method:'POST',body:JSON.stringify({contact_id:teacherSelected.value.id,content:teacherNewMsg.value})});var msg=teacherNewMsg.value;teacherNewMsg.value='';teacherChatMsgs.value.push({id:Date.now(),content:msg,sender_type:'counselor',created_at:new Date().toISOString()});await nextTick();if(teacherMsgRef.value)teacherMsgRef.value.scrollTop=teacherMsgRef.value.scrollHeight;loadMessageContacts()}catch(e){alert('发送失败')}
    }
    function openTeacherVideo(){if(!teacherSelected.value)return;initTeacherVideo();startTeacherVideo();if(socket){socket.emit('video_call_request',{student_id:teacherSelected.value.student_id,student_name:teacherSelected.value.name})}}

    // --- 心理测评 ---
    const assessmentOptions=['完全不会','几天','一半以上','几乎每天'];
    const phq9Questions=[
        {text:'做事时提不起劲或没有兴趣'},{text:'感到心情低落、沮丧或绝望'},
        {text:'入睡困难、睡不安稳或睡眠过多'},{text:'感觉疲倦或没有活力'},
        {text:'食欲不振或吃太多'},{text:'觉得自己很糟，或觉得自己很失败'},
        {text:'对事物专注有困难，例如阅读或看电视'},{text:'动作或说话速度缓慢到别人已经觉察，或正好相反'},
        {text:'有不如死掉或用某种方式伤害自己的念头'},
    ];
    const gad7Questions=[
        {text:'感觉紧张、焦虑或急切'},{text:'不能够停止或控制担忧'},
        {text:'对各种各样的事情担忧过多'},{text:'很难放松下来'},
        {text:'由于不安而无法静坐'},{text:'变得容易烦恼或急躁'},
        {text:'感到似乎将有可怕的事情发生'},
    ];
    const isiQuestions=[
        {text:'入睡困难的程度'},{text:'夜间易醒或早醒的程度'},
        {text:'比期望的时间早醒的程度'},{text:'对自己的睡眠状况是否满意'},
        {text:'睡眠问题对日间功能的影响程度'},{text:'他人是否注意到你的睡眠问题'},{text:'对睡眠问题的担忧程度'},
    ];
    const assessmentAnswers=ref(Array(23).fill(-1));
    const assessmentSubmitting=ref(false);
    const assessmentResult=ref(null);
    const assessmentHistory=ref([]);
    const assessStartTime=ref(0);
    function initAssessment(){assessmentAnswers.value=Array(23).fill(-1);assessmentResult.value=null;assessStartTime.value=Date.now();loadAssessmentHistory()}
    async function submitAssessment(){
        var duration=Math.floor((Date.now()-assessStartTime.value)/1000);
        assessmentSubmitting.value=true;
        var answers=[];
        for(var i=0;i<23;i++){answers.push({q:i+1,a:assessmentAnswers.value[i]})}
        try{var d=await api('/assessment/submit',{method:'POST',body:JSON.stringify({answers:answers,duration_seconds:duration})});
            if(d.success){assessmentResult.value=d.data;loadAssessmentHistory();showToast('测评完成','success')}else{alert(d.message||'提交失败')}
        }catch(e){alert('提交失败')}
        assessmentSubmitting.value=false
    }
    function resetAssessment(){assessmentResult.value=null;initAssessment()}
    async function loadAssessmentHistory(){
        try{var d=await api('/assessment/history');assessmentHistory.value=d.data||[]}catch(e){}
    }

    // --- 班会策划 ---
    const meetingTheme=ref('');const meetingResult=ref('');const meetingLoading=ref(false);
    async function generateMeeting(){if(!meetingTheme.value.trim())return;meetingLoading.value=true;try{var d=await api('/conversation/organize',{method:'POST',body:JSON.stringify({scene:'班会策划',content:meetingTheme.value})});meetingResult.value=d.content||d.result||'生成失败'}catch(e){meetingResult.value='请求失败'}meetingLoading.value=false}

    // --- 公文写作 ---
    const docType=ref('通知');const docContent=ref('');const docResult=ref('');const docLoading=ref(false);
    async function generateDoc(){if(!docContent.value.trim())return;docLoading.value=true;try{var d=await api('/conversation/organize',{method:'POST',body:JSON.stringify({scene:'公文写作',content:'文种：'+docType.value+'\n\n内容：'+docContent.value})});docResult.value=d.content||d.result||'生成失败'}catch(e){docResult.value='请求失败'}docLoading.value=false}
    let socket=null;
    function initSocket(){if(socket||typeof io==='undefined')return;socket=io({transports:['polling','websocket']});socket.on('connect',function(){console.log('WS connected')});socket.on('connect_error',function(err){console.log('WS error:',err.message)});socket.on('new_message',function(msg){if(selectedContact.value){chatMessages.value.push(msg);nextTick(function(){if($refs.studentChatMsg)$refs.studentChatMsg.scrollTop=$refs.studentChatMsg.scrollHeight})}loadUnreadCount();loadMessageContacts()})}
    async function loadStudentData(){try{var d=await api('/counselors/list');counselors.value=d.data||[]}catch(e){console.error('加载辅导员列表失败',e)}loadMessageContacts();loadUnreadCount()}
    async function loadMessageContacts(){try{var d=await api('/messages/contacts');messageContacts.value=d.data||[]}catch(e){}}
    async function selectContact(contact){if(selectedContact.value&&socket){socket.emit('leave',{room:'chat_'+selectedContact.value.id})}selectedContact.value=contact;if(socket){socket.emit('join',{room:'chat_'+contact.id})}try{var d=await api('/messages/'+contact.id);chatMessages.value=(d.data||[]).reverse();await nextTick();if($refs.studentChatMsg)$refs.studentChatMsg.scrollTop=$refs.studentChatMsg.scrollHeight;loadMessageContacts()}catch(e){}}
    async function sendMessage(){if(!newMessage.value.trim()||!selectedContact.value)return;try{var d=await api('/messages/send',{method:'POST',body:JSON.stringify({contact_id:selectedContact.value.id,content:newMessage.value})});if(socket&&d.success){socket.emit('send_message',{room:'chat_'+selectedContact.value.id,message:{id:d.data?d.data.id:null,content:newMessage.value,sender_type:'student',created_at:new Date().toISOString()}})}newMessage.value='';selectContact(selectedContact.value)}catch(e){alert('发送失败')}}
    async function loadUnreadCount(){try{var d=await api('/messages/unread');studentUnreadCount.value=d.data?d.data.unread_count:0}catch(e){}}
    async function loadAppointments(){try{var d=await api('/appointments');appointments.value=d.data||[]}catch(e){}}
    async function createAppointment(){if(!newAppointment.counselor_id||!newAppointment.appointment_time){alert('请选择辅导员和预约时间');return}try{await api('/appointments/create',{method:'POST',body:JSON.stringify(newAppointment)});showToast('预约创建成功','success');newAppointment.counselor_id='';newAppointment.appointment_time='';newAppointment.reason='';loadAppointments()}catch(e){alert('预约失败')}}
    function formatTime(timeStr){if(!timeStr)return'';var d=new Date(timeStr);return d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0')}

    // --- 学生端视频通话（完整WebRTC）---
    const localVideo=ref(null);const remoteVideo=ref(null);const isInCall=ref(false);const isVideoEnabled=ref(true);const isAudioEnabled=ref(true);const videoCallStatus=ref('等待连接...');let localStream=null;let peerConnection=null;const callRoom=ref('');
    var videoListenersSet=false;
    function initStudentVideo(){
        if(!socket||videoListenersSet)return;videoListenersSet=true;
        socket.on('video_call_accepted',function(data){callRoom.value=data.room;socket.emit('join',{room:data.room});videoCallStatus.value='已连接，建立通话...';createPeerConn();createOffer()});
        socket.on('video_offer',function(data){if(!peerConnection)createPeerConn();if(peerConnection.signalingState==='stable'){peerConnection.setRemoteDescription(new RTCSessionDescription(data)).then(function(){createAnswer()}).catch(function(e){console.log(e)})}});
        socket.on('video_answer',function(data){if(peerConnection&&peerConnection.signalingState==='have-local-offer'){peerConnection.setRemoteDescription(new RTCSessionDescription(data)).catch(function(e){console.log(e)})}});
        socket.on('video_ice_candidate',function(data){if(peerConnection&&peerConnection.remoteDescription&&data.candidate&&data.candidate.candidate){peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate)).catch(function(e){})}});
        socket.on('video_call_ended',function(){endVideoCall()});
    }
    function createPeerConn(){
        if(peerConnection){peerConnection.close();peerConnection=null}
        peerConnection=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
        if(localStream)localStream.getTracks().forEach(function(t){peerConnection.addTrack(t,localStream)});
        peerConnection.onicecandidate=function(e){if(e.candidate&&e.candidate.candidate)socket.emit('video_ice_candidate',{candidate:e.candidate,room:callRoom.value})};
        peerConnection.ontrack=function(e){if(remoteVideo.value&&e.streams[0]){remoteVideo.value.srcObject=e.streams[0];videoCallStatus.value='视频通话中'}};
    }
    async function createOffer(){if(!peerConnection||peerConnection.signalingState!=='stable')return;var offer=await peerConnection.createOffer();await peerConnection.setLocalDescription(offer);socket.emit('video_offer',{type:offer.type,sdp:offer.sdp,room:callRoom.value})}
    async function createAnswer(){if(!peerConnection||peerConnection.signalingState!=='have-remote-offer')return;var answer=await peerConnection.createAnswer();await peerConnection.setLocalDescription(answer);socket.emit('video_answer',{type:answer.type,sdp:answer.sdp,room:callRoom.value})}
    async function startVideoCall(){
        if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){alert('您的浏览器不支持摄像头/麦克风，请使用Chrome或Edge浏览器');return}
        try{
            // 先检查设备权限状态
            var perms=await navigator.permissions.query({name:'camera'}).catch(function(){return null});
            if(perms&&perms.state==='denied'){alert('摄像头权限已被拒绝，请在浏览器设置中允许摄像头访问');return}
            localStream=await navigator.mediaDevices.getUserMedia({video:{width:640,height:480},audio:true});
            isInCall.value=true;isVideoEnabled.value=true;isAudioEnabled.value=true;videoCallStatus.value='等待老师接听...';
            await nextTick();
            if(localVideo.value)localVideo.value.srcObject=localStream;
            if(!socket){showToast('连接未就绪，请刷新页面','error');return}
            initStudentVideo();callRoom.value='video_'+Date.now();socket.emit('join',{room:callRoom.value});socket.emit('video_call_request',{student_id:currentUser.student_id,student_name:currentUser.name,room:callRoom.value});
        }catch(err){
            if(err.name==='NotAllowedError'){alert('摄像头或麦克风权限被拒绝，请在浏览器地址栏左侧点击锁图标→允许摄像头和麦克风')}
            else if(err.name==='NotFoundError'){alert('未检测到摄像头或麦克风设备，请连接设备后重试')}
            else if(err.name==='NotReadableError'){alert('摄像头或麦克风被其他应用占用，请关闭其他视频应用后重试')}
            else{alert('无法访问摄像头或麦克风：'+err.message)}
        }
    }
    function endVideoCall(){
        if(localStream){localStream.getTracks().forEach(function(t){t.stop()});localStream=null}
        if(peerConnection){peerConnection.close();peerConnection=null}
        if(localVideo.value)localVideo.value.srcObject=null;if(remoteVideo.value)remoteVideo.value.srcObject=null;
        isInCall.value=false;videoCallStatus.value='等待连接...';
        if(socket)socket.emit('video_call_end',{room:callRoom.value});
    }
    function toggleVideo(){if(localStream){var videoTrack=localStream.getVideoTracks()[0];if(videoTrack){videoTrack.enabled=!videoTrack.enabled;isVideoEnabled.value=videoTrack.enabled}}}
    function toggleAudio(){if(localStream){var audioTrack=localStream.getAudioTracks()[0];if(audioTrack){audioTrack.enabled=!audioTrack.enabled;isAudioEnabled.value=audioTrack.enabled}}}

    // --- 老师端视频 + YOLO ---
    const teacherLocalVideo=ref(null);const teacherRemoteVideo=ref(null);const yoloCanvas=ref(null);
    const teacherInCall=ref(false);const teacherVideoEnabled=ref(true);const teacherAudioEnabled=ref(true);
    const teacherVideoStatus=ref('等待连接...');const incomingCall=ref(null);
    let teacherLocalStream=null;let teacherPeerConn=null;const videoRoom=ref('teacher_room');

    const yoloActive=ref(false);const currentYoloEmotion=ref(null);const yoloAlerts=ref([]);
    let yoloTimer=null;

    function initTeacherVideo(){
        loadYoloLogs();
        if(socket){
            socket.on('incoming_video_call',function(data){incomingCall.value=data;showToast('收到 '+data.student_name+' 的视频呼叫','info')});
            socket.on('video_call_accepted',function(data){teacherVideoStatus.value='已连接';createTeacherPeerConn();createTeacherOffer()});
            socket.on('video_offer',function(data){if(!teacherPeerConn)createTeacherPeerConn();if(teacherPeerConn.signalingState==='stable'){teacherPeerConn.setRemoteDescription(new RTCSessionDescription(data)).then(function(){createTeacherAnswer()}).catch(function(e){console.log(e)})}});
            socket.on('video_answer',function(data){if(teacherPeerConn&&teacherPeerConn.signalingState==='have-local-offer'){teacherPeerConn.setRemoteDescription(new RTCSessionDescription(data)).catch(function(e){console.log(e)})}});
            socket.on('video_ice_candidate',function(data){if(teacherPeerConn&&teacherPeerConn.remoteDescription&&data.candidate&&data.candidate.candidate){teacherPeerConn.addIceCandidate(new RTCIceCandidate(data.candidate)).catch(function(e){})}});
            socket.on('video_call_ended',function(){endTeacherVideo()});
        }
    }
    async function startTeacherVideo(){
        if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia){alert('您的浏览器不支持摄像头/麦克风，请使用Chrome或Edge浏览器');return}
        try{
            var perms=await navigator.permissions.query({name:'camera'}).catch(function(){return null});
            if(perms&&perms.state==='denied'){alert('摄像头权限已被拒绝，请在浏览器设置中允许摄像头访问');return}
            teacherLocalStream=await navigator.mediaDevices.getUserMedia({video:{width:640,height:480},audio:true});
            teacherInCall.value=true;teacherVideoEnabled.value=true;teacherAudioEnabled.value=true;
            teacherVideoStatus.value='等待学生连接...';videoRoom.value='video_'+Date.now();
            await nextTick();
            if(teacherLocalVideo.value)teacherLocalVideo.value.srcObject=teacherLocalStream;
            if(socket){socket.emit('join',{room:videoRoom.value})}
            showToast('视频已开启，等待学生接入','info');
        }catch(err){
            if(err.name==='NotAllowedError'){alert('摄像头或麦克风权限被拒绝，请在浏览器地址栏左侧点击锁图标→允许摄像头和麦克风')}
            else if(err.name==='NotFoundError'){alert('未检测到摄像头或麦克风设备')}
            else if(err.name==='NotReadableError'){alert('摄像头或麦克风被其他应用占用，请关闭其他视频应用后重试')}
            else{alert('无法访问摄像头：'+err.message)}
        }
    }
    function createTeacherPeerConn(){
        if(teacherPeerConn){teacherPeerConn.close();teacherPeerConn=null}
        teacherPeerConn=new RTCPeerConnection({iceServers:[{urls:'stun:stun.l.google.com:19302'}]});
        if(teacherLocalStream)teacherLocalStream.getTracks().forEach(function(t){teacherPeerConn.addTrack(t,teacherLocalStream)});
        teacherPeerConn.onicecandidate=function(e){if(e.candidate&&e.candidate.candidate)socket.emit('video_ice_candidate',{candidate:e.candidate,room:videoRoom.value})};
        teacherPeerConn.ontrack=function(e){if(teacherRemoteVideo.value&&e.streams[0]){teacherRemoteVideo.value.srcObject=e.streams[0];teacherVideoStatus.value='视频通话中'}};
    }
    async function createTeacherOffer(){
        if(!teacherPeerConn||teacherPeerConn.signalingState!=='stable')return;
        var offer=await teacherPeerConn.createOffer();await teacherPeerConn.setLocalDescription(offer);
        socket.emit('video_offer',{type:offer.type,sdp:offer.sdp,room:videoRoom.value});
    }
    async function createTeacherAnswer(){
        if(!teacherPeerConn||teacherPeerConn.signalingState!=='have-remote-offer')return;
        var answer=await teacherPeerConn.createAnswer();await teacherPeerConn.setLocalDescription(answer);
        socket.emit('video_answer',{type:answer.type,sdp:answer.sdp,room:videoRoom.value});
    }
    function acceptVideoCall(){
        if(!teacherInCall.value)startTeacherVideo();
        if(incomingCall.value){videoRoom.value=incomingCall.value.room||("video_"+Date.now());socket.emit("join",{room:videoRoom.value});socket.emit("video_call_accept",{room:videoRoom.value});incomingCall.value=null}
    }
    function rejectVideoCall(){incomingCall.value=null;showToast('已拒绝视频呼叫','info')}
    function endTeacherVideo(){
        if(teacherLocalStream){teacherLocalStream.getTracks().forEach(function(t){t.stop()});teacherLocalStream=null}
        if(teacherPeerConn){teacherPeerConn.close();teacherPeerConn=null}
        if(teacherLocalVideo.value)teacherLocalVideo.value.srcObject=null;
        if(teacherRemoteVideo.value)teacherRemoteVideo.value.srcObject=null;
        teacherInCall.value=false;teacherVideoStatus.value='等待连接...';stopYolo();
        socket.emit('video_call_end',{room:videoRoom.value});
    }
    function toggleTeacherVideo(){if(teacherLocalStream){var t=teacherLocalStream.getVideoTracks()[0];if(t){t.enabled=!t.enabled;teacherVideoEnabled.value=t.enabled}}}
    function toggleTeacherAudio(){if(teacherLocalStream){var t=teacherLocalStream.getAudioTracks()[0];if(t){t.enabled=!t.enabled;teacherAudioEnabled.value=t.enabled}}}

    // YOLO 情绪监测
    function toggleYolo(){if(yoloActive.value)stopYolo();else startYolo()}
    function startYolo(){
        if(!teacherRemoteVideo.value||!teacherRemoteVideo.value.srcObject){showToast('请先连接视频','error');return}
        yoloActive.value=true;currentYoloEmotion.value=null;captureYoloFrame();
        showToast('YOLO 情绪监测已开启','success');
    }
    function stopYolo(){yoloActive.value=false;if(yoloTimer)clearTimeout(yoloTimer);yoloTimer=null}
    function captureYoloFrame(){
        if(!yoloActive.value||!teacherRemoteVideo.value)return;
        try{
            var canvas=document.createElement('canvas');var video=teacherRemoteVideo.value;
            canvas.width=video.videoWidth||320;canvas.height=video.videoHeight||240;
            var ctx=canvas.getContext('2d');ctx.drawImage(video,0,0,canvas.width,canvas.height);
            var b64=canvas.toDataURL('image/jpeg',0.7);
            // 发送到后端 YOLO 分析
            var h={};if(tk.value)h['Authorization']='Bearer '+tk.value;
            fetch(API+'/emotion/yolo-detect',{method:'POST',headers:{'Content-Type':'application/json',...h},body:JSON.stringify({image:b64})})
            .then(function(r){return r.json()})
            .then(function(d){
                if(d.success&&d.emotions&&d.emotions.length>0){
                    var e=d.emotions[0];currentYoloEmotion.value={emotion:e.primary_emotion,confidence:e.confidence};
                    if(d.high_risk_alerts&&d.high_risk_alerts.length>0){
                        d.high_risk_alerts.forEach(function(a){yoloAlerts.value.unshift(a)});
                        if(yoloAlerts.value.length>50)yoloAlerts.value=yoloAlerts.value.slice(0,50);
                    }
                }
            }).catch(function(){});
        }catch(e){}
        yoloTimer=setTimeout(captureYoloFrame,2000);
    }
    async function loadYoloLogs(){try{var d=await api('/emotion/yolo-logs?limit=20');if(d.data)yoloAlerts.value=d.data}catch(e){}}
    function yoloEmotionIcon(e){var m={高兴:'😊',正常:'😐',平静:'😌',焦虑:'😰',恐惧:'😨',愤怒:'😡',悲伤:'😢',压抑:'😞',紧张:'😬',惊讶:'😲'};return m[e]||'🤔'}
    function yoloEmotionColor(e){var c={高兴:'var(--success)',正常:'var(--text-secondary)',平静:'var(--info)',焦虑:'var(--warning)',恐惧:'var(--danger)',愤怒:'var(--danger)',悲伤:'var(--warning)',压抑:'var(--danger)'};return c[e]||'var(--text-secondary)'}
    function formatYoloTime(ts){if(!ts)return'';var d=new Date(ts);return d.getHours().toString().padStart(2,'0')+':'+d.getMinutes().toString().padStart(2,'0')+':'+d.getSeconds().toString().padStart(2,'0')}

    // ===== 学生端 Widget =====
    // 喝水
    const waterCount=ref(0);const waterProgress=computed(function(){return waterCount.value/8});
    function loadWater(){var today=new Date().toISOString().split('T')[0];var saved=localStorage.getItem('water_'+today);waterCount.value=saved?parseInt(saved):0}
    function addWater(){if(waterCount.value<8){waterCount.value++;var today=new Date().toISOString().split('T')[0];localStorage.setItem('water_'+today,waterCount.value);showToast('+1 杯水！继续加油 💧','success')}}
    function resetWater(){waterCount.value=0;var today=new Date().toISOString().split('T')[0];localStorage.setItem('water_'+today,'0');showToast('今日饮水已重置','info')}
    // 灵感
    const dailyQuote=ref(QUOTES[new Date().getDate()%QUOTES.length]);
    // 英语
    const dailyWord=ref(WORDS[new Date().getDate()%WORDS.length]);
    // 心情
    const todayMood=ref('');const todayMoodText=computed(function(){return MOOD_LABELS[todayMood.value]||'点击记录今天的心情吧 🌈'});
    function loadMood(){var today=new Date().toISOString().split('T')[0];var saved=localStorage.getItem('mood_'+today);todayMood.value=saved||''}
    function recordMood(mood){todayMood.value=mood;var today=new Date().toISOString().split('T')[0];localStorage.setItem('mood_'+today,mood);showToast('心情已记录！','success')}

    // ===== 个性化工作台 =====
    const editLayout=ref(false);
    const dashboardLayout=ref(JSON.parse(localStorage.getItem('dashboard_layout')||'["stats","highRisk","mediumRisk","todos","calendar","todoList"]'));
    function layoutVisible(id){return dashboardLayout.value.indexOf(id)>-1}
    function toggleLayoutItem(id){var idx=dashboardLayout.value.indexOf(id);if(idx>-1)dashboardLayout.value.splice(idx,1);else dashboardLayout.value.push(id);localStorage.setItem('dashboard_layout',JSON.stringify(dashboardLayout.value))}

    // --- 生命周期 ---
    onMounted(function(){
        if(isLoggedIn.value){
            if(localStorage.getItem('user_type')==='student'){currentUser.role='student';page.value='studentHome';setRole();loadStudentData();}
            else{loadDash();loadWorkplan();setInterval(loadDash,30000);}
        }
        loadWater();loadMood();
        // 设置角色属性
        if(currentUser.role){setRole();}
    });
    watch(page,function(p){if(p==='dashboard')loadWorkplan();if(p==='students')loadStudents();if(p==='reminders')loadReminders();if(p==='emotionBoard')loadEmotionDashboard();if(p==='teacherChat'){initSocket();loadMessageContacts();initTeacherVideo()}if(p==='studentChat'){initSocket();loadMessageContacts()}});
    watch(function(){return currentUser.role},function(r){if(r)setRole()});

    return {isLoggedIn,loginForm,loginLoading,currentUser,roleLabel,handleLogin,handleLogout,isDarkMode,toggleTheme,loginType,showStudentRegister,studentLoginForm,studentRegisterForm,handleStudentLogin,handleStudentRegister,
        page,dash,recentAlerts,loadDash,chatScene,chatHistory,chatInput,chatLoading,chatMsg,sendChat,clearImage,previewUrl,selectedFile,uploadAndRecognize,handlePaste,handleFileUpload,emoLogs,emoResult,loadEmotionLogs,uploadAudio,loadKbStats,alerts,loadAlerts,ackAlert,kbStats,uploadDoc,students,studentSearch,showAddStudent,newStudent,selectedStudent,studentProfiles,loadStudents,addStudent,viewStudent,updateStudentNotes,wp,wpRiskStudents,wpCalYear,wpCalMonth,wpCalRows,wpCalPrev,wpCalNext,wpSelectDay,loadWorkplan,wpCompleteTodo,wpTodoStudent,wpTodoWork,showAddTodo,newTodo,addCustomTodo,completeCustomTodo,reminders,showCompleted,loadReminders,completeReminder,emoDashStats,emoDashAlerts,emoPieChart,emoRiskChart,emoTrendChart,emoHeatmapChart,loadEmotionDashboard,calDayDetail,clickCalDay,emoColor,riskBg,riskLbl,renderMd,chatInputPlaceholder,
        messageContacts,selectedContact,chatMessages,newMessage,studentUnreadCount,appointments,counselors,newAppointment,loadMessageContacts,selectContact,sendMessage,loadAppointments,createAppointment,formatTime,
        localVideo,remoteVideo,isInCall,isVideoEnabled,isAudioEnabled,videoCallStatus,startVideoCall,endVideoCall,toggleVideo,toggleAudio,
        teacherLocalVideo,teacherRemoteVideo,yoloCanvas,teacherInCall,teacherVideoEnabled,teacherAudioEnabled,teacherVideoStatus,incomingCall,initTeacherVideo,startTeacherVideo,endTeacherVideo,toggleTeacherVideo,toggleTeacherAudio,acceptVideoCall,rejectVideoCall,
        yoloActive,currentYoloEmotion,yoloAlerts,toggleYolo,startYolo,stopYolo,loadYoloLogs,yoloEmotionIcon,yoloEmotionColor,formatYoloTime,
        svgIcon,sidebarCollapsed,sidebarMobileOpen,toggleSidebar,pageTitle,toasts,showToast,todayStr,greetingText,
        waterCount,waterProgress,addWater,resetWater,loadWater,dailyQuote,dailyWord,todayMood,todayMoodText,recordMood,loadMood,emojiList,showEmoji,insertEmoji,teacherShowEmoji,insertTeacherEmoji,teacherSelected,teacherChatMsgs,teacherNewMsg,teacherUnreadCount,teacherMsgRef,selectTeacherContact,sendTeacherMsg,openTeacherVideo,guidanceResult,guidanceLoading,analyzeCounselorGuidance,studentSearchQuery,studentSearchResults,searchStudents,inviteStudent,meetingTheme,meetingResult,meetingLoading,generateMeeting,docType,docContent,docResult,docLoading,generateDoc,assessmentAnswers,assessmentOptions,assessmentSubmitting,assessmentResult,assessmentHistory,phq9Questions,gad7Questions,isiQuestions,initAssessment,submitAssessment,resetAssessment,loadAssessmentHistory,
        showAddTodo,newTodo,addCustomTodo,completeCustomTodo
    };
}}).mount('#app');
}catch(e){document.getElementById('app').innerHTML='<div style="padding:40px;color:red"><h2>JS Error</h2><pre>'+e.message+'</pre></div>';}})();
