import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Activity, Boxes, Cpu, LayoutDashboard, MessageSquare, Monitor, Settings, ListTodo, Folder, PanelLeftClose} from 'lucide-react';
import {getHealth} from './api';
import './style.css';
import {AccountGate} from './AccountGate';
import {Devices} from './Devices';
import {Tasks} from './Tasks';
import {Services} from './Services';
import {Workspaces} from './Workspaces';
import {Assistant} from './Assistant';
import {SpeechSettings} from './SpeechSettings';
import {ActivityFeed} from './ActivityFeed';
import {Overview} from './Overview';
import {VirtualIoT} from './VirtualIoT';

const pages = [
  ['Overview', LayoutDashboard], ['Assistant', MessageSquare], ['Devices', Monitor],
  ['Workspaces', Folder], ['Tasks', ListTodo], ['Services', Boxes],
  ['Activity', Activity], ['Virtual IoT', Cpu], ['Settings', Settings], ['Настройки ассистента', Settings],
] as const;

function App() {
  const [page, setPage] = useState('Overview');
  const [online, setOnline] = useState(false);
  const [error, setError] = useState('');
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    let live = true;
    const refresh = () => getHealth().then(h => {if(live){setOnline(h.status === 'ok');setError('');}})
      .catch(e => {if(live){setOnline(false);setError(String(e.message));}});
    refresh(); const interval = setInterval(refresh, 5000);
    return () => {live = false; clearInterval(interval);};
  }, []);
  return <div className={collapsed ? 'shell collapsed' : 'shell'}>
    <aside><a className="brand" href="#" onClick={() => setPage('Overview')}><span className="symbol">Δ</span><span className="nav-label">DELTA <small>PERSONAL ECOSYSTEM</small></span></a>
      <div className="section-label nav-label">CONTROL CENTER</div><nav>{pages.map(([name, Icon]) => <button title={name} className={page === name ? 'active' : ''} key={name} onClick={() => setPage(name)}><Icon size={18}/><span className="nav-label">{name}</span></button>)}</nav>
      <footer><span className={online ? 'dot online' : 'dot'}/><span className="nav-label">Core {online ? 'online' : 'offline'}</span><button title="Свернуть меню" onClick={() => setCollapsed(!collapsed)}><PanelLeftClose size={16}/></button></footer>
    </aside>
    <main><header><span>Personal / <strong>{page}</strong></span><span className="version">LOCAL ENVIRONMENT <span>v0.1</span></span></header>
      <section className="content"><div className="eyebrow">DELTA DIGITAL ECOSYSTEM</div><h1>{page === 'Overview' ? 'Your workspace. Connected.' : page}</h1><p className="subtitle">Единое пространство для ваших устройств, сервисов и идей.</p>
      {error && <div role="alert" className="error">Core недоступен: {error}</div>}
      {page === 'Настройки ассистента' ? <SpeechSettings/> : page === 'Activity' ? <ActivityFeed/> : page === 'Virtual IoT' ? <VirtualIoT/> : page === 'Assistant' ? <Assistant/> : page === 'Workspaces' ? <Workspaces onAssistant={()=>setPage('Assistant')}/> : page === 'Tasks' ? <Tasks/> : page === 'Services' ? <Services/> : page === 'Devices' ? <Devices/> : page === 'Settings' ? <article><h2>Настройки</h2><p>Вы вошли в аккаунт администратора. Подключение защищено серверной сессией.</p><label className="debug-toggle"><input type="checkbox" defaultChecked={sessionStorage.getItem('delta-debug')==='true'} onChange={e=>sessionStorage.setItem('delta-debug',String(e.target.checked))}/> Показывать диагностику ответов</label></article> :
       <Overview online={online}/> }
      </section><div className="bottom-note">Δ &nbsp; A personal digital ecosystem.</div></main>
  </div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><AccountGate><App/></AccountGate></React.StrictMode>);
