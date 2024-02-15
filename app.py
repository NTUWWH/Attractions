import csv
import threading
from time import sleep
import bisect
from flask import Flask, jsonify, render_template, redirect, url_for
from datetime import datetime


class Vote:
    def __init__(self, user_id, feedback):
        self.user_id = user_id
        self.feedback = feedback
        self.timestamp = datetime.now()
        self.saved_to_csv = False

class Attraction:
    def __init__(self, attraction_id, country, city, name, category, child_friendly, accessible):
        self.attraction_id = attraction_id
        self.country = country
        self.city = city
        self.name = name
        self.category = category
        self.child_friendly = child_friendly
        self.accessible = accessible
        self.votes = 0
        self.user_votes = []

    def add_vote(self, user_id, feedback):
        self.user_votes.append(Vote(user_id, feedback))
        self.votes += 1

    def has_voted(self, user_id):
        for vote in self.user_votes:
            if vote.user_id == user_id:
                return True
        return False

    def __lt__(self, other):
        # 比较两个景点的名称
        return self.name < other.name

class Country:
    def __init__(self, name):
        self.name = name
        self.attractions = []  # 所有景点
        self.sorted_attractions = []  # 按名称排序的景点列表

    def add_sorted_attraction(self, attraction):
        self.attractions.append(attraction)
        index = bisect.bisect_left([name for name, _ in self.sorted_attractions], attraction.name)
        self.sorted_attractions.insert(index, (attraction.name, attraction))

class TourismGraph:
    def __init__(self):
        self.sorted_countries = []
        self.attractions = []
        self.next_attraction_id = 1
        self.user_count = 0
        self.user_votes_index = []
        self.queue_lock = threading.Lock()  # 线程锁，用于同步访问队列
        self.start_background_tasks()

    def start_background_tasks(self):
        # 启动后台线程处理队列中的项目
        thread = threading.Thread(target=self.process_queues)
        thread.daemon = True
        thread.start()

    def process_queues(self):
        while True:
            sleep(60)
            with self.queue_lock:
                # 保存景点和投票信息到CSV，不再使用队列
                self.save_data_to_csv('attractions.csv', self.attractions, is_attraction=True)
                self.save_data_to_csv('votes.csv', self.attractions, is_attraction=False)
                print(f"CSV files updated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def save_data_to_csv(self, filename, data, is_attraction):
        with open(filename, 'w', newline='') as csvfile:  # 使用'w'模式，每次都覆盖文件
            writer = csv.writer(csvfile)
            if is_attraction:
                headers = ['Attraction ID', 'Country', 'City', 'Name', 'Category', 'Child Friendly', 'Accessible',
                           'Votes']
                writer.writerow(headers)
                for attraction in data:
                    writer.writerow([
                        attraction.attraction_id,
                        attraction.country,
                        attraction.city,
                        attraction.name,
                        attraction.category,
                        attraction.child_friendly,
                        attraction.accessible,
                        attraction.votes
                    ])
                    # 不需要检查 saved_to_csv 或将其设置为 True，因为我们每次都写入所有景点
            else:
                headers = ['Attraction ID', 'User ID', 'Feedback', 'Timestamp']
                if csvfile.tell() == 0:  # 检查文件是否为空，如果为空则写入表头
                    writer.writerow(headers)
                for attraction in data:
                    for vote in attraction.user_votes:
                        if not vote.saved_to_csv:  # 对于投票数据，仍然检查 saved_to_csv 以避免重复
                            writer.writerow([
                                attraction.attraction_id,
                                vote.user_id,
                                vote.feedback,
                                vote.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                            ])
                            vote.saved_to_csv = True  # 标记为已保存，避免重复写入

    def find_or_add_country(self, country_name):
        index = bisect.bisect_left(self.sorted_countries, (country_name,))
        if index < len(self.sorted_countries) and self.sorted_countries[index][0] == country_name:
            return self.sorted_countries[index][1]
        new_country = Country(country_name)
        bisect.insort_left(self.sorted_countries, (country_name, new_country))
        return new_country

    def add_attraction(self, country_name, city, name, category,  child_friendly, accessible):
        country = self.find_or_add_country(country_name)
        new_attraction = Attraction(self.next_attraction_id, country_name, city, name, category, child_friendly, accessible)
        country.add_sorted_attraction(new_attraction)
        self.attractions.append(new_attraction)
        self.next_attraction_id += 1
        print(f"Attraction '{name}' has been created.")
        return new_attraction.attraction_id

    def vote_for_attraction(self, attraction_name, user_id, feedback):
        for country in self.sorted_countries:
            country_obj = country[1]
            index = bisect.bisect_left(country_obj.sorted_attractions, (attraction_name,))
            if index < len(country_obj.sorted_attractions) and country_obj.sorted_attractions[index][
                0] == attraction_name:
                attraction = country_obj.sorted_attractions[index][1]
                if not attraction.has_voted(user_id):
                    attraction.add_vote(user_id, feedback)
                    self.update_user_votes_index(user_id, attraction)
                    print(f"Attraction '{attraction_name}' has been voted by {user_id}.")
                    return
        raise ValueError(f"Attraction '{attraction_name}' does not exist.")

    def update_user_votes_index(self, user_id, attraction):
        for entry in self.user_votes_index:
            if entry[0] == user_id:
                entry[1].append(attraction)
                return
        self.user_votes_index.append([user_id, [attraction]])
        
    def get_user_votes(self, user_id):
        full_records = []
        for entry in self.user_votes_index:
            if entry[0] == user_id:
                for attraction in entry[1]:  # 遍历用户投票的所有景点
                    for vote in attraction.user_votes:
                        if vote.user_id == user_id:
                            # 为每个投票记录添加完整的景点信息
                            record = {
                                "country": attraction.country,
                                "city": attraction.city,
                                "attraction_name": attraction.name,
                                "category": attraction.category,
                                "child_friendly": attraction.child_friendly,
                                "accessible": attraction.accessible,
                                "feedback": vote.feedback,
                                "timestamp": vote.timestamp.strftime('%Y-%m-%d %H:%M:%S')  # 格式化时间
                            }
                            full_records.append(record)
        return full_records
        
    def filter_attractions(self, country_name=None, category=None, child_friendly=None, accessible=None):
        filtered_attractions = []
        for attraction in self.attractions:
            if (country_name is None or attraction.country.name == country_name) and \
                    (category is None or attraction.category == category) and \
                    (child_friendly is None or attraction.child_friendly == child_friendly) and \
                    (accessible is None or attraction.accessible == accessible):
                filtered_attractions.append(attraction)
        return filtered_attractions

    def generate_new_user_id(self):
        self.user_count += 1
        return self.user_count


from flask import request, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

tourism_graph = TourismGraph()

category_mapping = {
    'category1': 'Natural attractions',
    'category2': 'Historical attractions',
    'category3': 'Urban attractions',
    'category4': 'Theme park',
    'category5': 'Outdoor activity attractions',
    'category6': 'Food spots',
    'category7': 'Vacation spot',
    'category8': 'Arts and Performance',
    'category9': 'Gym',
    'category10': 'Characteristic towns'
}

@app.route('/add_attraction', methods=['POST'])
def add_attraction():
    data = request.json
    country_name = data.get('country_name')
    city = data.get('city')
    name = data.get('attraction_name')
    category = data.get('category')
    category = category_mapping[category]
    child_friendly = data.get('child_friendly', False)
    accessible = data.get('accessible', False)
    print(data)

    if not all([country_name, name, category, city]):
        return jsonify({"error": "Missing required fields."}), 400
    try:
        attraction_id = tourism_graph.add_attraction(country_name, city, name, category, child_friendly, accessible)
        return jsonify({"message": "Attraction added successfully", "attraction_id": attraction_id}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route('/vote_for_attraction', methods=['POST'])
def vote_for_attraction():
    user_id = request.cookies.get('userID')
    if not user_id:
        return jsonify({"error": "User not identified."}), 403

    data = request.json
    attraction_name = data.get('attraction_name')
    feedback = data.get('feedback')

    if not all([attraction_name, feedback]):
        return jsonify({"error": "Missing required fields."}), 400

    try:
        tourism_graph.vote_for_attraction(attraction_name, user_id, feedback)
        return jsonify({"message": "Vote recorded successfully"}), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route('/get_user_votes', methods=['GET'])
def get_user_votes():
    user_id = request.cookies.get('userID')
    if not user_id:
        return jsonify({"error": "User not identified."}), 403

    # 调用后端函数以获取当前用户的投票记录
    voted_attractions = tourism_graph.get_user_votes(user_id)

    # 修改列表推导式以包括所有返回的字段
    votes_data = [
        {
            "country": vote["country"],
            "city": vote["city"],
            "attraction_name": vote["attraction_name"],
            "category": vote["category"],
            "child_friendly": "Yes" if vote["child_friendly"] else "No",
            "accessible": "Yes" if vote["accessible"] else "No",
            "feedback": vote["feedback"],
            "timestamp": vote["timestamp"]
        }
        for vote in voted_attractions
    ]

    return jsonify(votes_data), 200


@app.route('/')
def index():
    user_id = request.cookies.get('userID')
    if not user_id:
        user_id = str(tourism_graph.generate_new_user_id())
        response = make_response(redirect(url_for('home')))
        response.set_cookie('userID', user_id)
        return response
    else:
        return redirect(url_for('home'))


@app.route('/top_attractions', methods=['GET'])
def get_top_attractions():
    top_attractions = sorted(tourism_graph.attractions, key=lambda x: x.votes, reverse=True)[:10]
    attractions_data = [
        {
            "name": attr.name,
            "country": attr.country,
            "city": attr.city,
            "votes": attr.votes,
            "category": attr.category,
            "child_friendly": attr.child_friendly,
            "accessible": attr.accessible
        }
        for attr in top_attractions
    ]
    return jsonify(attractions_data), 200

@app.route('/latest_comments', methods=['GET'])
def get_latest_comments():
    all_votes = []
    for attraction in tourism_graph.attractions:
        for vote in attraction.user_votes:
            all_votes.append((vote, attraction))  # Pair each vote with its attraction

    # Sort all votes by timestamp, descending
    sorted_votes = sorted(all_votes, key=lambda x: x[0].timestamp, reverse=True)
    latest_votes = sorted_votes[:3]  # Get the latest 5 votes

    comments_data = [
        {
            "attraction_name": vote_attr[1].name,  # Use the attraction name from the paired tuple
            "country": vote_attr[1].country,  # Add country name
            "city": vote_attr[1].city,  # Add city name
            "feedback": vote_attr[0].feedback,  # Use the feedback from the Vote object
            "timestamp": vote_attr[0].timestamp.strftime('%Y-%m-%d %H:%M:%S')
        }
        for vote_attr in latest_votes
    ]

    return jsonify(comments_data), 200

@app.route('/attractions', methods=['GET'])
def get_all_attractions():
    # 获取所有景点信息
    attractions_data = [
        {
            "name": attr.name,
            "country": attr.country,
            "city": attr.city,
            "votes": attr.votes,
            "category": attr.category,
            "child_friendly": attr.child_friendly,
            "accessible": attr.accessible
        }
        for attr in tourism_graph.attractions  # 直接遍历所有景点
    ]
    return jsonify(attractions_data), 200

@app.route('/index')
def home():
    return render_template('index.html')

@app.route('/submit')
def add():
    return render_template('submit.html')

@app.route('/vote')
def vote():
    return render_template('vote.html')

@app.route('/view')
def view():
    return render_template('view.html')

if __name__ == '__main__':
    app.run(host='localhost', port=5000)


