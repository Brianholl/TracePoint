import datetime
import json
import asyncio
import uuid
from pathlib import Path

from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
import markdown

from config import config
from database import (
    init_db, get_session, Search, save_search, update_search,
    User, get_user_by_dni, get_user_by_id, create_user, count_users
)
from modules.auth import (
    hash_password, verify_password,
    create_session_token, verify_session_token,
    create_confidential_token, verify_confidential_token,
    generate_totp_secret, get_totp_uri, generate_totp_qr_svg, verify_totp
)
from translations import t, get_language
from modules.search_usernames import search_username
from modules.search_email import search_email
from modules.search_name import search_name
from modules.search_phone import search_phone
from modules.search_social import analyze_social_profiles
from modules.search_deepweb import search_deepweb
from modules.ai_analyzer import analyze_results
from modules.report_generator import generate_report
from modules.holehe_checker import check_holehe
from modules.google_dorker import google_dork_search
from modules.url_tools import analyze_url
from modules.breach_checker import check_breaches
from modules.image_search import reverse_image_search, search_people_engines
from modules.image_social_search import search_social_by_image
from modules.social_instagram import scrape_instagram
from modules.social_twitter import scrape_twitter
from modules.social_facebook import scrape_facebook
from modules.social_linkedin import scrape_linkedin
from modules.social_telegram import scrape_telegram
from modules.social_discord import scrape_discord
from modules.accounts_config import (
    load_accounts, save_accounts, get_account_schema,
    get_all_configured, ACCOUNT_SCHEMAS
)

app = FastAPI(title='TracePoint', version='2.0.0')

templates = Jinja2Templates(directory=Path(__file__).parent / 'templates')
templates.env.filters['markdown'] = lambda text: markdown.markdown(text or '', extensions=['extra'])

def ctx(request: Request, **extra):
    lang = get_language(request)
    theme = request.cookies.get('theme', 'dark')
    def _t(key: str) -> str:
        return t(request, key)
    return {
        'request': request,
        'lang': lang,
        'theme': theme if theme in ('dark','light') else 'dark',
        't': _t,
        **extra,
    }

async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> User | None:
    token = request.cookies.get('session')
    if not token:
        return None
    dni = verify_session_token(token)
    if not dni:
        return None
    return await get_user_by_dni(session, dni)

app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')

@app.on_event('startup')
async def startup():
    await init_db()

# ─── Auth Routes ────────────────────────────────────────────

@app.get('/auth/register', response_class=HTMLResponse)
async def register_page(request: Request, session: AsyncSession = Depends(get_session)):
    user_count = await count_users(session)
    return templates.TemplateResponse('register.html', ctx(request, is_first=(user_count == 0)))

@app.post('/auth/register', response_class=HTMLResponse)
async def register_action(
    request: Request,
    dni: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    existing = await get_user_by_dni(session, dni)
    if existing:
        return templates.TemplateResponse('register.html', ctx(request, error='DNI already registered', is_first=False))
    pwd_hash = hash_password(password)
    user = await create_user(session, dni.strip(), display_name.strip(), pwd_hash)
    token = create_session_token(user.dni)
    resp = RedirectResponse(url='/auth/2fa/setup', status_code=303)
    resp.set_cookie('session', token, httponly=True, max_age=604800, samesite='lax')
    return resp

@app.get('/auth/login', response_class=HTMLResponse)
async def login_page(request: Request, session: AsyncSession = Depends(get_session)):
    user_count = await count_users(session)
    if user_count == 0:
        return RedirectResponse(url='/auth/register', status_code=303)
    return templates.TemplateResponse('login.html', ctx(request))

@app.post('/auth/login', response_class=HTMLResponse)
async def login_action(
    request: Request,
    dni: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = await get_user_by_dni(session, dni.strip())
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse('login.html', ctx(request, error='Invalid DNI or password'))
    token = create_session_token(user.dni)
    resp = RedirectResponse(url='/', status_code=303)
    resp.set_cookie('session', token, httponly=True, max_age=604800, samesite='lax')
    return resp

@app.get('/auth/logout')
async def logout():
    resp = RedirectResponse(url='/', status_code=303)
    resp.delete_cookie('session')
    resp.delete_cookie('confidential')
    return resp

@app.get('/auth/2fa/setup', response_class=HTMLResponse)
async def twofa_setup_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url='/auth/login', status_code=303)
    if not user.totp_secret:
        user.totp_secret = generate_totp_secret()
        session.add(user)
        await session.commit()
    qr_svg = generate_totp_qr_svg(user.totp_secret, user.dni)
    return templates.TemplateResponse('2fa_setup.html', ctx(request, qr_svg=qr_svg, user=user))

@app.post('/auth/2fa/setup', response_class=HTMLResponse)
async def twofa_setup_verify(
    request: Request,
    code: str = Form(...),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url='/auth/login', status_code=303)
    if not user.totp_secret:
        user.totp_secret = generate_totp_secret()
    if verify_totp(user.totp_secret, code.strip()):
        user.totp_enabled = True
        await session.commit()
        return RedirectResponse(url='/', status_code=303)
    qr_svg = generate_totp_qr_svg(user.totp_secret, user.dni)
    return templates.TemplateResponse('2fa_setup.html', ctx(request, qr_svg=qr_svg, user=user, error='Invalid code, try again'))

@app.post('/auth/2fa/skip')
async def twofa_skip(
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url='/auth/login', status_code=303)
    if user.totp_secret and not user.totp_enabled:
        user.totp_enabled = False
        await session.commit()
    return RedirectResponse(url='/', status_code=303)

# ─── Confidential Folder ────────────────────────────────────

@app.get('/confidential', response_class=HTMLResponse)
async def confidential_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url='/auth/login', status_code=303)
    conf_token = request.cookies.get('confidential')
    if conf_token:
        uid = verify_confidential_token(conf_token)
        if uid == user.id:
            result = await session.execute(
                select(Search).where(
                    Search.user_id == user.id,
                    Search.visibility == 'confidential'
                ).order_by(desc(Search.id))
            )
            searches = result.scalars().all()
            return templates.TemplateResponse('confidential.html', ctx(request, searches=searches, user=user))

    if user.totp_enabled:
        return templates.TemplateResponse('2fa_verify.html', ctx(request, user=user))
    else:
        conf_token = create_confidential_token(user.id)
        resp = RedirectResponse(url='/confidential', status_code=303)
        resp.set_cookie('confidential', conf_token, httponly=True, max_age=900, samesite='lax')
        return resp

@app.post('/confidential/verify', response_class=HTMLResponse)
async def confidential_verify(
    request: Request,
    code: str = Form(...),
    redirect: str = Form(None),
    user: User | None = Depends(get_current_user),
):
    if not user:
        return RedirectResponse(url='/auth/login', status_code=303)
    if not user.totp_enabled or not user.totp_secret:
        return RedirectResponse(url='/confidential', status_code=303)
    if verify_totp(user.totp_secret, code.strip()):
        conf_token = create_confidential_token(user.id)
        target = redirect or '/confidential'
        resp = RedirectResponse(url=target, status_code=303)
        resp.set_cookie('confidential', conf_token, httponly=True, max_age=900, samesite='lax')
        return resp
    return templates.TemplateResponse('2fa_verify.html', ctx(request, user=user, error='Invalid code', redirect_url=redirect))

# ─── Core Routes ────────────────────────────────────────────

@app.get('/', response_class=HTMLResponse)
async def index(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    result = await session.execute(
        select(Search).where(Search.visibility == 'public').order_by(desc(Search.id)).limit(10)
    )
    recent = result.scalars().all()
    accounts = get_all_configured()
    return templates.TemplateResponse('index.html', ctx(request, recent=recent, accounts=accounts, user=user))

@app.get('/search', response_class=HTMLResponse)
async def search_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    accounts = get_all_configured()
    return templates.TemplateResponse('search.html', ctx(request, accounts=accounts, user=user))

@app.get('/deep-search', response_class=HTMLResponse)
async def deep_search_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    accounts = get_all_configured()
    return templates.TemplateResponse('deep_search.html', ctx(request, accounts=accounts, user=user))

@app.get('/history', response_class=HTMLResponse)
async def history(
    request: Request,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    if user:
        result = await session.execute(
            select(Search).where(
                (Search.visibility == 'public') | (Search.user_id == user.id)
            ).order_by(desc(Search.id))
        )
    else:
        result = await session.execute(
            select(Search).where(Search.visibility == 'public').order_by(desc(Search.id))
        )
    searches = result.scalars().all()
    return templates.TemplateResponse('history.html', ctx(request, searches=searches, user=user))

@app.post('/search/run')
async def run_search(
    request: Request,
    query_type: str = Form(...),
    query_value: str = Form(...),
    photo: UploadFile = File(None),
    visibility: str = Form('public'),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    image_path = None
    if photo and photo.filename:
        ext = Path(photo.filename).suffix or '.jpg'
        fname = f'{uuid.uuid4().hex}{ext}'
        image_path = config.UPLOADS_DIR / fname
        content = await photo.read()
        image_path.write_bytes(content)
    search = await save_search(
        session, query_type, query_value,
        user_id=user.id if user else None,
        visibility=visibility
    )
    asyncio.create_task(execute_search(search.id, query_type, query_value, image_path))
    return RedirectResponse(url=f'/results/{search.id}', status_code=303)

@app.post('/deep-search/run')
async def run_deep_search(
    request: Request,
    username: str = Form(''),
    email: str = Form(''),
    full_name: str = Form(''),
    phone: str = Form(''),
    urls: str = Form(''),
    photo: UploadFile = File(None),
    visibility: str = Form('public'),
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    inputs = []
    if username: inputs.append(('username', username.strip()))
    if email: inputs.append(('email', email.strip()))
    if full_name: inputs.append(('name', full_name.strip()))
    if phone: inputs.append(('phone', phone.strip()))
    if urls:
        for u in urls.strip().split('\n'):
            u = u.strip()
            if u: inputs.append(('url', u))

    image_path = None
    if photo and photo.filename:
        ext = Path(photo.filename).suffix or '.jpg'
        fname = f'{uuid.uuid4().hex}{ext}'
        image_path = config.UPLOADS_DIR / fname
        content = await photo.read()
        image_path.write_bytes(content)

    query_value = ' | '.join([f'{itype}:{v}' for itype, v in inputs])
    if image_path:
        query_value += f' | photo:{fname}'
    search = await save_search(
        session, 'deep', query_value[:500],
        user_id=user.id if user else None,
        visibility=visibility
    )
    asyncio.create_task(execute_deep_search(search.id, inputs, image_path))
    return RedirectResponse(url=f'/results/{search.id}', status_code=303)

@app.get('/results/{search_id}', response_class=HTMLResponse)
async def results(
    request: Request,
    search_id: int,
    session: AsyncSession = Depends(get_session),
    user: User | None = Depends(get_current_user),
):
    search = await session.get(Search, search_id)
    if not search:
        return HTMLResponse('<h1>Search not found</h1>', status_code=404)

    if search.visibility == 'confidential':
        if not user or search.user_id != user.id:
            return HTMLResponse('<h1>Access denied</h1>', status_code=403)
        conf_token = request.cookies.get('confidential')
        if not conf_token or verify_confidential_token(conf_token) != user.id:
            if user.totp_enabled:
                return templates.TemplateResponse('2fa_verify.html', ctx(request, user=user,
                    redirect_url=f'/results/{search_id}'))
            conf_token = create_confidential_token(user.id)
            resp = RedirectResponse(request.url.path, status_code=303)
            resp.set_cookie('confidential', conf_token, httponly=True, max_age=900, samesite='lax')
            return resp

    created_at = search.created_at
    if isinstance(created_at, str):
        created_at = datetime.datetime.fromisoformat(created_at)
    search.created_at = created_at

    return templates.TemplateResponse('results.html', ctx(request, search=search, user=user))

@app.get('/accounts', response_class=HTMLResponse)
async def accounts_page(
    request: Request,
    user: User | None = Depends(get_current_user),
):
    accounts = load_accounts()
    schemas = {k: v for k, v in ACCOUNT_SCHEMAS.items()}
    return templates.TemplateResponse('accounts.html', ctx(request, accounts=accounts, schemas=schemas, user=user))

@app.post('/accounts/save')
async def save_accounts_form(request: Request):
    form = await request.form()
    data = {}
    for key, value in form.multi_items():
        if key.startswith('account_'):
            parts = key.split('_', 2)
            if len(parts) == 3:
                platform = parts[1]
                field = parts[2]
                if platform not in data:
                    data[platform] = {'enabled': False}
                data[platform][field] = value

    for platform in data:
        if f'enable_{platform}' in form:
            data[platform]['enabled'] = True

    save_accounts(data)
    return RedirectResponse(url='/accounts', status_code=303)

@app.get('/view-report/{search_id}')
async def view_report(search_id: int, session: AsyncSession = Depends(get_session)):
    search = await session.get(Search, search_id)
    if not search or not search.report_path:
        return HTMLResponse('<h1>Report not found</h1>', status_code=404)
    report_path = Path(search.report_path)
    if report_path.exists():
        return FileResponse(str(report_path), media_type='text/html')
    return HTMLResponse('<h1>Report file not found on disk</h1>', status_code=404)

@app.get('/print-report/{search_id}', response_class=HTMLResponse)
async def print_report(
    request: Request,
    search_id: int,
    session: AsyncSession = Depends(get_session),
):
    search = await session.get(Search, search_id)
    if not search:
        return HTMLResponse('<h1>Not found</h1>', status_code=404)

    created_at = search.created_at
    if isinstance(created_at, str):
        created_at = datetime.datetime.fromisoformat(created_at)
    search.created_at = created_at

    return templates.TemplateResponse('print_report.html', ctx(request, search=search, created_at=created_at))

@app.get('/uploads/{filename}')
async def serve_upload(filename: str):
    file_path = config.UPLOADS_DIR / filename
    if file_path.exists():
        return FileResponse(str(file_path))
    return HTMLResponse('<h1>File not found</h1>', status_code=404)

# ─── Background Tasks ───────────────────────────────────────

async def execute_search(search_id: int, query_type: str, query_value: str, image_path: Path = None):
    async for session in get_session():
        try:
            search_data = {
                'query_type': query_type,
                'query_value': query_value,
                'results': {},
            }

            if image_path and image_path.exists():
                image_url = f'/uploads/{image_path.name}'
                image_social = await search_social_by_image(
                    image_path=str(image_path), image_url=image_url
                )
                if image_social:
                    search_data['results']['image_social'] = image_social

            if query_type == 'username':
                username_results = await search_username(query_value)
                search_data['results'] = username_results

                social_analysis = await analyze_social_profiles(
                    query_value, username_results.get('profiles', [])
                )
                if social_analysis:
                    search_data['results']['social_analysis'] = social_analysis

                deepweb = await search_deepweb(query_value)
                if deepweb and deepweb.get('tor_connected'):
                    search_data['results']['deep_web'] = deepweb

            elif query_type == 'email':
                email_results = await search_email(query_value)
                search_data['results'] = email_results

                holehe = await check_holehe(query_value)
                if holehe:
                    search_data['results']['holehe'] = holehe

            elif query_type == 'name':
                name_results = await search_name(query_value)
                search_data['results'] = name_results

            elif query_type == 'phone':
                phone_results = await search_phone(query_value)
                search_data['results'] = phone_results

            ai_analysis = await analyze_results(search_data, image_path=str(image_path) if image_path else None)
            search_data['ai_analysis'] = ai_analysis

            report_path = generate_report({
                'id': search_id,
                'query_type': query_type,
                'query_value': query_value,
                'results': search_data['results'],
                'ai_analysis': ai_analysis,
                'created_at': datetime.datetime.utcnow(),
                'accounts_used': get_all_configured(),
            })

            await update_search(
                session, search_id,
                status='completed',
                results=search_data['results'],
                ai_analysis=ai_analysis,
                report_path=report_path,
                completed_at=datetime.datetime.utcnow(),
            )

        except Exception as e:
            await update_search(
                session, search_id,
                status='error',
                error=str(e)[:1000],
                completed_at=datetime.datetime.utcnow(),
            )

async def execute_deep_search(search_id: int, inputs: list, image_path: Path = None):
    async for session in get_session():
        try:
            all_results = {}
            query_parts = []

            if image_path and image_path.exists():
                image_url = f'/uploads/{image_path.name}'
                image_social = await search_social_by_image(
                    image_path=str(image_path), image_url=image_url
                )
                if image_social:
                    all_results['image_social'] = image_social

            for input_type, value in inputs:
                query_parts.append(f'{input_type}:{value}')

                if input_type == 'username':
                    username_results = await search_username(value)
                    all_results[f'username_{value}'] = username_results

                    social_analysis = await analyze_social_profiles(
                        value, username_results.get('profiles', [])
                    )
                    if social_analysis:
                        all_results[f'social_analysis_{value}'] = social_analysis

                    instagram = await scrape_instagram(value)
                    if not instagram.get('error'):
                        all_results[f'instagram_{value}'] = instagram

                    twitter = await scrape_twitter(value)
                    if twitter.get('profile'):
                        all_results[f'twitter_{value}'] = twitter

                    deepweb = await search_deepweb(value)
                    if deepweb and deepweb.get('tor_connected'):
                        all_results[f'deepweb_{value}'] = deepweb

                elif input_type == 'email':
                    email_results = await search_email(value)
                    all_results[f'email_{value}'] = email_results

                    holehe = await check_holehe(value)
                    if holehe:
                        all_results[f'holehe_{value}'] = holehe

                    breaches = await check_breaches(value, 'email')
                    if breaches:
                        all_results[f'breaches_{value}'] = breaches

                    dork = await google_dork_search(value, categories=['emails', 'data_leaks'])
                    if dork.get('total_results', 0) > 0:
                        all_results[f'dorks_{value}'] = dork

                elif input_type == 'name':
                    name_results = await search_name(value)
                    all_results[f'name_{value}'] = name_results

                    dork = await google_dork_search(value)
                    if dork.get('total_results', 0) > 0:
                        all_results[f'dorks_{value}'] = dork

                    facebook = await scrape_facebook(value, 'profile')
                    if facebook.get('profiles_found'):
                        all_results[f'facebook_{value}'] = facebook

                    linkedin = await scrape_linkedin(value)
                    if linkedin.get('profiles'):
                        all_results[f'linkedin_{value}'] = linkedin

                elif input_type == 'phone':
                    phone_results = await search_phone(value)
                    all_results[f'phone_{value}'] = phone_results

                    dork = await google_dork_search(value, categories=['personal_info'])
                    if dork.get('total_results', 0) > 0:
                        all_results[f'dorks_{value}'] = dork

                elif input_type == 'url':
                    url_results = await analyze_url(value)
                    all_results[f'url_{value[:30]}'] = url_results

            combined_query = ' | '.join(query_parts)

            search_data = {
                'query_type': 'deep',
                'query_value': combined_query,
                'results': all_results,
            }

            ai_analysis = await analyze_results(search_data, image_path=str(image_path) if image_path else None)
            search_data['ai_analysis'] = ai_analysis

            report_path = generate_report({
                'id': search_id,
                'query_type': 'deep',
                'query_value': combined_query[:200],
                'results': all_results,
                'ai_analysis': ai_analysis,
                'created_at': datetime.datetime.utcnow(),
                'accounts_used': get_all_configured(),
            })

            await update_search(
                session, search_id,
                status='completed',
                results=all_results,
                ai_analysis=ai_analysis,
                report_path=report_path,
                completed_at=datetime.datetime.utcnow(),
            )

        except Exception as e:
            await update_search(
                session, search_id,
                status='error',
                error=str(e)[:1000],
                completed_at=datetime.datetime.utcnow(),
            )

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=8000, reload=True)
