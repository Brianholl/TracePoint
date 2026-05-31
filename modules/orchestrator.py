import datetime
from pathlib import Path

from database import get_session, update_search
from modules.accounts_config import get_all_configured
from modules.ai_analyzer import analyze_results
from modules.report_generator import generate_report
from modules.progress import publish as emit
from modules.search_usernames import search_username
from modules.search_email import search_email
from modules.search_name import search_name
from modules.search_phone import search_phone
from modules.search_social import analyze_social_profiles
from modules.search_deepweb import search_deepweb
from modules.holehe_checker import check_holehe
from modules.google_dorker import google_dork_search
from modules.url_tools import analyze_url
from modules.breach_checker import check_breaches
from modules.image_social_search import search_social_by_image
from modules.social_instagram import scrape_instagram
from modules.social_twitter import scrape_twitter
from modules.social_facebook import scrape_facebook
from modules.social_linkedin import scrape_linkedin


async def execute_search(search_id: int, query_type: str, query_value: str, image_path: Path = None):
    async for session in get_session():
        try:
            emit(search_id, '_pipeline', 'running', label='Búsqueda iniciada')
            search_data = {
                'query_type': query_type,
                'query_value': query_value,
                'results': {},
            }

            if image_path and image_path.exists():
                emit(search_id, 'image', 'running', label='Búsqueda inversa de imagen')
                image_url = f'/uploads/{image_path.name}'
                image_social = await search_social_by_image(
                    image_path=str(image_path), image_url=image_url
                )
                if image_social:
                    search_data['results']['image_social'] = image_social
                emit(search_id, 'image', 'done',
                     found=image_social.get('total_verified', 0) if image_social else 0)

            if query_type == 'username':
                emit(search_id, 'username', 'running', label='Usuario en plataformas')
                username_results = await search_username(query_value)
                search_data['results'] = username_results
                emit(search_id, 'username', 'done', found=username_results.get('total_found', 0))

                emit(search_id, 'social', 'running', label='Análisis de perfiles sociales')
                social_analysis = await analyze_social_profiles(
                    query_value, username_results.get('profiles', [])
                )
                if social_analysis:
                    search_data['results']['social_analysis'] = social_analysis
                emit(search_id, 'social', 'done')

                emit(search_id, 'deepweb', 'running', label='Deep web (Tor)')
                deepweb = await search_deepweb(query_value)
                if deepweb and deepweb.get('tor_connected'):
                    search_data['results']['deep_web'] = deepweb
                emit(search_id, 'deepweb', 'done')

            elif query_type == 'email':
                emit(search_id, 'email', 'running', label='Análisis de email')
                email_results = await search_email(query_value)
                search_data['results'] = email_results
                emit(search_id, 'email', 'done',
                     found=email_results.get('hibp', {}).get('total_breaches', 0) if email_results.get('hibp') else 0)

                emit(search_id, 'holehe', 'running', label='Holehe (registros)')
                holehe = await check_holehe(query_value)
                if holehe:
                    search_data['results']['holehe'] = holehe
                emit(search_id, 'holehe', 'done')

            elif query_type == 'name':
                emit(search_id, 'name', 'running', label='Búsqueda por nombre')
                name_results = await search_name(query_value)
                search_data['results'] = name_results
                emit(search_id, 'name', 'done', found=name_results.get('total_results', 0))

            elif query_type == 'phone':
                emit(search_id, 'phone', 'running', label='Análisis de teléfono')
                phone_results = await search_phone(query_value)
                search_data['results'] = phone_results
                emit(search_id, 'phone', 'done')

            emit(search_id, 'ai', 'running', label='Análisis IA')
            ai_analysis = await analyze_results(search_data, image_path=str(image_path) if image_path else None)
            search_data['ai_analysis'] = ai_analysis
            emit(search_id, 'ai', 'done')

            report_path = generate_report({
                'id': search_id,
                'query_type': query_type,
                'query_value': query_value,
                'results': search_data['results'],
                'ai_analysis': ai_analysis,
                'created_at': datetime.datetime.utcnow(),
                'accounts_used': get_all_configured(),
            })
            emit(search_id, 'report', 'done', label='Reporte generado')

            await update_search(
                session, search_id,
                status='completed',
                results=search_data['results'],
                ai_analysis=ai_analysis,
                report_path=report_path,
                completed_at=datetime.datetime.utcnow(),
            )
            emit(search_id, '_pipeline', 'completed', label='Investigación completa')

        except Exception as e:
            await update_search(
                session, search_id,
                status='error',
                error=str(e)[:1000],
                completed_at=datetime.datetime.utcnow(),
            )
            emit(search_id, '_pipeline', 'error', error=str(e)[:200])


async def execute_deep_search(search_id: int, inputs: list, image_path: Path = None):
    async for session in get_session():
        try:
            emit(search_id, '_pipeline', 'running', label='Investigación profunda iniciada')
            all_results = {}
            query_parts = []

            if image_path and image_path.exists():
                emit(search_id, 'image', 'running', label='Búsqueda inversa de imagen')
                image_url = f'/uploads/{image_path.name}'
                image_social = await search_social_by_image(
                    image_path=str(image_path), image_url=image_url
                )
                if image_social:
                    all_results['image_social'] = image_social
                emit(search_id, 'image', 'done',
                     found=image_social.get('total_verified', 0) if image_social else 0)

            for input_type, value in inputs:
                query_parts.append(f'{input_type}:{value}')
                node = f'{input_type}:{value}'
                emit(search_id, node, 'running', label=f'{input_type}: {value}')

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

                    emit(search_id, node, 'done', found=username_results.get('total_found', 0))

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

                    emit(search_id, node, 'done')

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

                    emit(search_id, node, 'done', found=name_results.get('total_results', 0))

                elif input_type == 'phone':
                    phone_results = await search_phone(value)
                    all_results[f'phone_{value}'] = phone_results

                    dork = await google_dork_search(value, categories=['personal_info'])
                    if dork.get('total_results', 0) > 0:
                        all_results[f'dorks_{value}'] = dork

                    emit(search_id, node, 'done')

                elif input_type == 'url':
                    url_results = await analyze_url(value)
                    all_results[f'url_{value[:30]}'] = url_results
                    emit(search_id, node, 'done')

            combined_query = ' | '.join(query_parts)

            search_data = {
                'query_type': 'deep',
                'query_value': combined_query,
                'results': all_results,
            }

            emit(search_id, 'ai', 'running', label='Análisis IA')
            ai_analysis = await analyze_results(search_data, image_path=str(image_path) if image_path else None)
            search_data['ai_analysis'] = ai_analysis
            emit(search_id, 'ai', 'done')

            report_path = generate_report({
                'id': search_id,
                'query_type': 'deep',
                'query_value': combined_query[:200],
                'results': all_results,
                'ai_analysis': ai_analysis,
                'created_at': datetime.datetime.utcnow(),
                'accounts_used': get_all_configured(),
            })
            emit(search_id, 'report', 'done', label='Reporte generado')

            await update_search(
                session, search_id,
                status='completed',
                results=all_results,
                ai_analysis=ai_analysis,
                report_path=report_path,
                completed_at=datetime.datetime.utcnow(),
            )
            emit(search_id, '_pipeline', 'completed', label='Investigación completa')

        except Exception as e:
            await update_search(
                session, search_id,
                status='error',
                error=str(e)[:1000],
                completed_at=datetime.datetime.utcnow(),
            )
            emit(search_id, '_pipeline', 'error', error=str(e)[:200])
